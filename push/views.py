from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import PushSubscription
from .serializers import EndpointSerializer, KeySerializer, SubscriptionSerializer


@extend_schema(responses={200: KeySerializer, 503: None})
@api_view(['GET'])
def public_key(request):
    """The public key a browser needs to turn on push (503 if push isn't set up)."""
    if not settings.VAPID_PUBLIC_KEY:
        return Response({'detail': 'Push notifications are not set up on this server.'}, status=503)
    return Response({'key': settings.VAPID_PUBLIC_KEY})


@extend_schema(request=SubscriptionSerializer, responses={201: None, 200: None})
@api_view(['POST'])
def subscribe(request):
    """Save this device's push address for the logged-in user. A device that
    was used by someone else before now belongs to whoever is logged in."""
    serializer = SubscriptionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    _, created = PushSubscription.objects.update_or_create(
        endpoint=data['endpoint'],
        defaults={'user': request.user, 'p256dh': data['keys']['p256dh'], 'auth': data['keys']['auth']},
    )
    return Response(status=201 if created else 200)


@extend_schema(request=EndpointSerializer, responses={204: None})
@api_view(['POST'])
def unsubscribe(request):
    """Stop pushing to this device (used when signing out or turning push off)."""
    serializer = EndpointSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    PushSubscription.objects.filter(user=request.user, endpoint=serializer.validated_data['endpoint']).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
