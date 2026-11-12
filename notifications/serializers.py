from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor = serializers.SlugRelatedField(slug_field='username', read_only=True)
    message = serializers.ReadOnlyField()

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'message', 'actor', 'event_title', 'event_start', 'read', 'created']


class NotificationListSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
    notifications = NotificationSerializer(many=True)
