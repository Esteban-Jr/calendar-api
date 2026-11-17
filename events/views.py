from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from notifications.models import Notification
from notifications.notify import notify
from . import feeds
from .models import Event, Feed, Share
from .serializers import EventSerializer, FeedSerializer, InviteAgainSerializer
from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .permissions import IsOwnerOrReadOnly
import requests
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
            .select_related('owner', 'feed')
            .prefetch_related('shares__user')
        )
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            qs = qs.filter(end__gte=start)
        if end:
            qs = qs.filter(start__lte=end)
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


class FeedViewSet(viewsets.ModelViewSet):
    """My calendar links (CO/BE18). Adding one reads it straight away and its
    events show in my calendar, read-only. Deleting it removes them."""

    serializer_class = FeedSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    REFRESH_GAP = timedelta(seconds=60)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # building the API docs
            return Feed.objects.none()
        return Feed.objects.filter(owner=self.request.user).annotate(event_count=Count('events')).order_by('name', 'id')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            events = feeds.read(feeds.fetch(serializer.validated_data['url']))
        except feeds.FeedError as error:
            raise ValidationError({'url': [str(error)]})
        with transaction.atomic():
            feed = serializer.save(owner=request.user, last_fetched=timezone.now())
            feeds.import_events(feed, events)
        return Response(self.get_serializer(feed).data, status=201)

    def perform_update(self, serializer):
        feed = serializer.save()
        feed.events.update(color=feed.color)

    @extend_schema(request=None, responses={200: FeedSerializer})
    @action(detail=True, methods=['post'])
    def refresh(self, request, pk=None):
        """Read the link again now. 502 if the website fails (the events stay
        as they were); 429 if it was tried less than a minute ago."""
        feed = self.get_object()
        if feed.last_fetched and timezone.now() - feed.last_fetched < self.REFRESH_GAP:
            return Response({'detail': 'This link was refreshed less than a minute ago. Try again soon.'}, status=429)
        try:
            feeds.refresh(feed)
        except feeds.FeedError as error:
            return Response({'detail': str(error)}, status=502)
        return Response(self.get_serializer(self.get_queryset().get(pk=feed.pk)).data)  # fresh event_count
