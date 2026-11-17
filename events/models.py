from django.db import models
from django.contrib.auth.models import User

# The cake colours an event can have. The web app owns the actual shades.
EVENT_COLORS = [
    ('strawberry', 'Strawberry'),
    ('peach', 'Peach'),
    ('vanilla', 'Vanilla'),
    ('pistachio', 'Pistachio'),
    ('mint', 'Mint'),
    ('blueberry', 'Blueberry'),
    ('lavender', 'Lavender'),
    ('bubblegum', 'Bubblegum'),
]

class Feed(models.Model):
    """A calendar link someone subscribed to (e.g. all of a club's games).
    The server reads it (see events/feeds.py) and keeps its events in step."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feeds')
    name = models.CharField(max_length=50)
    url = models.URLField(max_length=500)
    color = models.CharField(max_length=20, choices=EVENT_COLORS, default='blueberry')
    last_fetched = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'url'], name='one_feed_per_link')]

    def __str__(self):
        return f'{self.name} ({self.owner.username})'


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    reminder = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=20, choices=EVENT_COLORS, default='blueberry')
    # Who it's shared with. Each person has a Share saying whether they've
    # accepted, declined, or not answered the invite yet.
    shared_with = models.ManyToManyField(User, through='Share', related_name='shared_events', blank=True)
    # The start time a push reminder was last sent for (see push/). If the
    # event is moved, start no longer matches and the reminder goes out again.
    reminder_sent_for = models.DateTimeField(null=True, blank=True, editable=False)
    # Set on events imported from a calendar link. They're read-only: the
    # link is the source, and refreshing it adds, changes or removes them.
    feed = models.ForeignKey(Feed, null=True, blank=True, on_delete=models.CASCADE, related_name='events')
    feed_uid = models.CharField(max_length=255, blank=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['feed', 'feed_uid'], condition=models.Q(feed__isnull=False), name='one_event_per_feed_uid',
            ),
        ]


class Share(models.Model):
    """An event shared with one person, and their answer to the invite. The
    event only shows in their calendar once they've accepted."""

    WAITING = 'waiting'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    STATUSES = [(WAITING, 'Waiting for an answer'), (ACCEPTED, 'Accepted'), (DECLINED, 'Declined')]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shares')
    status = models.CharField(max_length=10, choices=STATUSES, default=WAITING)
    created = models.DateTimeField(auto_now_add=True)
    answered = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'user'], name='one_share_per_person')]

    def __str__(self):
        return f'{self.event.title} → {self.user.username} ({self.status})'
