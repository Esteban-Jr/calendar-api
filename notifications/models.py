from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):
    """Something that happened that a person should hear about, e.g. a friend
    removed their shared event. The event's title and start are copied in,
    because the event itself may be gone."""

    SHARE_REMOVED = 'share_removed'  # `actor` removed my event from their calendar
    EVENT_DELETED = 'event_deleted'  # `actor` deleted an event they had shared with me
    KINDS = [(SHARE_REMOVED, 'Removed your shared event'), (EVENT_DELETED, 'Deleted a shared event')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=KINDS)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    event_title = models.CharField(max_length=200)
    event_start = models.DateTimeField(null=True)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    @property
    def message(self) -> str:
        who = self.actor.username if self.actor else 'Someone'
        if self.kind == self.SHARE_REMOVED:
            return f'{who} removed “{self.event_title}” from their calendar'
        return f'{who} deleted “{self.event_title}”'

    def __str__(self):
        return f'To {self.user}: {self.message}'
