from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor = serializers.SlugRelatedField(slug_field='username', read_only=True)
    message = serializers.ReadOnlyField()
    # For an invite: "waiting" (show Accept / Decline), "accepted", "declined",
    # or "cancelled" (the event was deleted or un-shared). None for other kinds.
    invite_status = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'kind', 'message', 'actor', 'event', 'event_title', 'event_start', 'invite_status', 'read', 'created',
        ]

    def get_invite_status(self, notification) -> str | None:
        if notification.kind != Notification.INVITED:
            return None
        # {event id: my answer}, looked up once for the whole list by the view.
        answers = self.context.get('my_answers', {})
        return answers.get(notification.event_id, 'cancelled')


class NotificationListSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
    notifications = NotificationSerializer(many=True)
