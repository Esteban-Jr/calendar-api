from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from events.models import Event
from .models import Friendship, between
from .serializers import FriendListSerializer, FriendRequestSerializer, PersonSerializer
from .throttles import FriendRequestThrottle


def person(friendship, me):
    return {'id': friendship.id, 'username': friendship.other(me).username}


@extend_schema(methods=['GET'], responses=FriendListSerializer)
@extend_schema(methods=['POST'], request=FriendRequestSerializer, responses={201: PersonSerializer, 200: PersonSerializer})
@api_view(['GET', 'POST'])
@throttle_classes([FriendRequestThrottle])
def friends(request):
    """GET: my friends and pending requests. POST {"username"}: send a request."""
    me = request.user
    if request.method == 'GET':
        mine = Friendship.objects.filter(Q(from_user=me) | Q(to_user=me)).select_related('from_user', 'to_user')
        by_name = lambda f: f.other(me).username.lower()  # noqa: E731
        return Response({
            'friends': [person(f, me) for f in sorted(mine, key=by_name) if f.accepted],
            'incoming': [person(f, me) for f in sorted(mine, key=by_name) if not f.accepted and f.to_user == me],
            'outgoing': [person(f, me) for f in sorted(mine, key=by_name) if not f.accepted and f.from_user == me],
        })

    serializer = FriendRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    username = serializer.validated_data['username'].strip()
    other = User.objects.filter(username__iexact=username).first()
    if other is None:
        return Response({'username': [f'There is no user called "{username}".']}, status=400)
    if other == me:
        return Response({'username': ["You can't add yourself."]}, status=400)

    existing = between(me, other).first()
    if existing and existing.accepted:
        return Response({'username': [f"You're already friends with {other.username}."]}, status=400)
    if existing and existing.from_user == me:
        return Response({'username': [f'You already sent {other.username} a request.']}, status=400)
    if existing:
        # They had already asked me: asking back means yes.
        existing.accepted = True
        existing.save()
        return Response(person(existing, me), status=200)

    friendship = Friendship.objects.create(from_user=me, to_user=other)
    return Response(person(friendship, me), status=201)


@extend_schema(request=None, responses=PersonSerializer)
@api_view(['POST'])
def accept(request, pk):
    """Accept a request someone sent me."""
    friendship = get_object_or_404(Friendship, pk=pk, to_user=request.user, accepted=False)
    friendship.accepted = True
    friendship.save()
    return Response(person(friendship, request.user))


@extend_schema(responses={204: None})
@api_view(['DELETE'])
def remove(request, pk):
    """Decline a request, cancel one I sent, or unfriend. Unfriending also
    stops sharing events between us, in both directions."""
    me = request.user
    friendship = get_object_or_404(Friendship.objects.filter(Q(from_user=me) | Q(to_user=me)), pk=pk)
    other = friendship.other(me)
    with transaction.atomic():
        if friendship.accepted:
            for event in Event.objects.filter(owner=me, shared_with=other):
                event.shared_with.remove(other)
            for event in Event.objects.filter(owner=other, shared_with=me):
                event.shared_with.remove(me)
        friendship.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
