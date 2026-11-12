from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from events.models import Share

from .serializers import NotificationListSerializer, NotificationSerializer

LATEST = 50


@extend_schema(responses=NotificationListSerializer)
@api_view(['GET'])
def notification_list(request):
    """My latest notifications, newest first, and how many are unread."""
    mine = request.user.notifications.select_related('actor')
    my_answers = dict(Share.objects.filter(user=request.user).values_list('event_id', 'status'))
    return Response({
        'unread': mine.filter(read=False).count(),
        'notifications': NotificationSerializer(mine[:LATEST], many=True, context={'my_answers': my_answers}).data,
    })


@extend_schema(request=None, responses={204: None})
@api_view(['POST'])
def mark_read(request):
    """Mark all my notifications as read (done when the list is opened)."""
    request.user.notifications.filter(read=False).update(read=True)
    return Response(status=status.HTTP_204_NO_CONTENT)
