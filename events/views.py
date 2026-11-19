from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import DateTimeField
from rest_framework import viewsets, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from notifications.models import Notification
from notifications.notify import notify
from .models import Event, Share, Tag
from .serializers import EventSerializer, InviteAgainSerializer
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .permissions import IsOwnerOrReadOnly
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

def _date_param(request, name):
    """Read the ?start= / ?end= date filter. Django's own date-time parser is
    used (the same one the filter used before), so every format that worked
    still works. A value that isn't a real date gives a 400 naming `name`,
    instead of crashing with a 500. Missing or empty means no filter."""
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return DateTimeField().to_python(value)
    except DjangoValidationError:
        raise ValidationError({name: ['Enter a valid date and time, e.g. 2026-11-01T00:00:00Z.']})


def _tags_param(request):
    """The ?tags=work,football filter as tidy names (trimmed, lowercase, no
    blanks or repeats), the same way tags are saved. Empty means no filter."""
    value = request.query_params.get('tags', '')
    return sorted({name.strip().lower() for name in value.split(',') if name.strip()})


@extend_schema_view(list=extend_schema(parameters=[
    OpenApiParameter('start', str, description='Only events ending on or after this date/time, e.g. 2026-11-01T00:00:00Z'),
    OpenApiParameter('end', str, description='Only events starting on or before this date/time'),
    OpenApiParameter('tags', str, description='Comma-separated tag names, e.g. work,football: only my events with any of them'),
]))
class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        me = self.request.user
        # Your calendar holds your own events and the ones you've accepted. An
        # invite you haven't answered yet can still be opened (to look at it
        # before answering) but isn't in the list.
        answers = [Share.ACCEPTED] if self.action == 'list' else [Share.ACCEPTED, Share.WAITING]
        qs = (
            Event.objects.filter(Q(owner=me) | Q(shares__user=me, shares__status__in=answers))
            .distinct()
            .select_related('owner')
            .prefetch_related('shares__user', 'tags')
        )
        start = _date_param(self.request, 'start')
        end = _date_param(self.request, 'end')
        if start:
            qs = qs.filter(end__gte=start)
        if end:
            qs = qs.filter(start__lte=end)
        # Only my own tags count: a friend's shared event never carries them.
        names = _tags_param(self.request)
        if names:
            qs = qs.filter(tags__owner=me, tags__name__in=names)
        return qs

    def perform_create(self, serializer):
        event = serializer.save(owner=self.request.user)
        for share in Share.objects.filter(event=event).select_related('user'):
            notify(share.user, Notification.INVITED, self.request.user, event)

    def perform_update(self, serializer):
        # Compare who it's shared with before and after: new people get an
        # invite, and people taken off before they answered are told.
        before = {share.user_id: share for share in Share.objects.filter(event=serializer.instance).select_related('user')}
        event = serializer.save()
        after = {share.user_id: share for share in Share.objects.filter(event=event).select_related('user')}
        for user_id, share in before.items():
            if user_id not in after and share.status == Share.WAITING:
                notify(share.user, Notification.INVITE_CANCELLED, self.request.user, event)
        for user_id, share in after.items():
            if user_id not in before:
                notify(share.user, Notification.INVITED, self.request.user, event)

    def perform_destroy(self, event):
        # Tell everyone it was shared with (the event is gone after this):
        # people who accepted that it was deleted, people who hadn't answered
        # yet that the invite was cancelled. People who declined aren't told.
        shares = list(Share.objects.filter(event=event).select_related('user'))
        event.delete()
        for share in shares:
            if share.status == Share.ACCEPTED:
                notify(share.user, Notification.EVENT_DELETED, self.request.user, event)
            elif share.status == Share.WAITING:
                notify(share.user, Notification.INVITE_CANCELLED, self.request.user, event)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def leave(self, request, pk=None):
        """Remove an event someone shared with me from my calendar. Only I am
        taken off it; the owner keeps the event and is told."""
        event = self.get_object()  # 404 unless it's mine or shared with me
        if event.owner == request.user:
            return Response({'detail': 'This is your own event. Delete it instead.'}, status=400)
        share = Share.objects.get(event=event, user=request.user)
        if share.status != Share.ACCEPTED:
            return Response({'detail': "You haven't accepted this invite. Decline it instead."}, status=400)
        share.delete()
        notify(event.owner, Notification.SHARE_REMOVED, request.user, event)
        return Response(status=204)

    @extend_schema(responses=EventSerializer(many=True))
    @action(detail=False, methods=['get'])
    def invites(self, request):
        """Events shared with me that I haven't accepted or declined yet,
        soonest first. They aren't in my calendar until I accept."""
        waiting = (
            Event.objects.filter(shares__user=request.user, shares__status=Share.WAITING)
            .select_related('owner')
            .prefetch_related('shares__user')
            .order_by('start')
        )
        return Response(self.get_serializer(waiting, many=True).data)

    def _answer(self, pk, status):
        """Answer my invite to event `pk`, and tell the owner."""
        share = get_object_or_404(Share.objects.select_related('event__owner'), event_id=pk, user=self.request.user)
        if share.status != Share.WAITING:
            return share, Response({'detail': f'You already {share.status} this invite.'}, status=400)
        share.status = status
        share.answered = timezone.now()
        share.save(update_fields=['status', 'answered'])
        kind = Notification.INVITE_ACCEPTED if status == Share.ACCEPTED else Notification.INVITE_DECLINED
        notify(share.event.owner, kind, self.request.user, share.event)
        return share, None

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def accept(self, request, pk=None):
        """Accept an invite: the event goes into my calendar. Returns the event."""
        share, problem = self._answer(pk, Share.ACCEPTED)
        return problem or Response(self.get_serializer(share.event).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def decline(self, request, pk=None):
        """Decline an invite: the event never shows in my calendar."""
        share, problem = self._answer(pk, Share.DECLINED)
        return problem or Response(status=204)

    @extend_schema(request=InviteAgainSerializer, responses=EventSerializer)
    @action(detail=True, methods=['post'], url_path='invite-again')
    def invite_again(self, request, pk=None):
        """Owner only: send a fresh invite to someone who declined."""
        event = self.get_object()  # 403 unless it's mine (IsOwnerOrReadOnly)
        serializer = InviteAgainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        share = Share.objects.filter(event=event, user__username__iexact=username).select_related('user').first()
        if share is None:
            return Response({'username': [f'“{event.title}” isn\'t shared with {username}.']}, status=400)
        if share.status != Share.DECLINED:
            return Response({'username': [f'Only someone who declined can be invited again ({share.user.username} is {share.status}).']}, status=400)
        share.status = Share.WAITING
        share.answered = None
        share.save(update_fields=['status', 'answered'])
        notify(share.user, Notification.INVITED, request.user, event)
        # The event's shares were loaded before this change: load them again
        # so the answer shows the new status.
        event._prefetched_objects_cache = {}
        return Response(self.get_serializer(event).data)


@api_view(['GET'])
def holidays(request):
    year = request.query_params.get('year')
    if not year:
        return Response({'detail': 'year is required'}, status=400)
    if not year.isdigit():
        return Response({'detail': 'year must be a number'}, status=400)

    url = f'https://date.nager.at/api/v3/PublicHolidays/{year}/CO'
    try:
        r = requests.get(url, timeout=5)
    except requests.RequestException:
        return Response({'detail': 'Holiday service unavailable'}, status=502)

    if r.status_code != 200:
        return Response({'detail': 'Could not get holidays'}, status=502)

    result = [
        {'date': h['date'], 'title': h['localName'], 'name': h['name']}
        for h in r.json()
    ]
    return Response(result)


@extend_schema(responses={200: {'type': 'array', 'items': {'type': 'string'}}})
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def tags(request):
    """My tags that are on at least one of my events, A-Z. Unused tags drop
    off by themselves, so there's nothing to tidy up."""
    names = (
        Tag.objects.filter(owner=request.user, events__isnull=False)
        .values_list('name', flat=True).distinct().order_by('name')
    )
    return Response(list(names))
