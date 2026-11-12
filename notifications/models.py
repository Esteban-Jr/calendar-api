from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):
    """Something that happened that a person should hear about, e.g. a friend
    removed their shared event. The event's title and start are copied in,
    because the event itself may be gone."""

    SHARE_REMOVED = 'share_removed'  # `actor` removed my event from their calendar
    EVENT_DELETED = 'event_deleted'  # `actor` deleted an event they had shared with me
    INVITED = 'invited'  # `actor` shared an event with me: accept or decline it
    INVITE_ACCEPTED = 'invite_accepted'  # `actor` accepted my event
    INVITE_DECLINED = 'invite_declined'  # `actor` declined my event
    INVITE_CANCELLED = 'invite_cancelled'  # `actor` deleted or un-shared an event before I answered
    KINDS = [
        (SHARE_REMOVED, 'Removed your shared event'),
        (EVENT_DELETED, 'Deleted a shared event'),
        (INVITED, 'Invited you to an event'),
        (INVITE_ACCEPTED, 'Accepted your event'),
        (INVITE_DECLINED, 'Declined your event'),
        (INVITE_CANCELLED, 'Cancelled an invite'),
    ]
    MESSAGES = {
        SHARE_REMOVED: '{who} removed “{title}” from their calendar',
        EVENT_DELETED: '{who} deleted “{title}”',
        INVITED: '{who} invited you to “{title}”',
        INVITE_ACCEPTED: '{who} accepted “{title}”',
        INVITE_DECLINED: '{who} declined “{title}”',
        INVITE_CANCELLED: '{who} cancelled “{title}”',
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=KINDS)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    # The event it's about, while it still exists (an invite needs it to be answered).
    event = models.ForeignKey('events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    event_title = models.CharField(max_length=200)
    event_start = models.DateTimeField(null=True)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    @property
    def message(self) -> str:
        who = self.actor.username if self.actor else 'Someone'
        return self.MESSAGES[self.kind].format(who=who, title=self.event_title)

    def __str__(self):
        return f'To {self.user}: {self.message}'
