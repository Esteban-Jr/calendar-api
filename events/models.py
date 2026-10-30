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

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    reminder = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=20, choices=EVENT_COLORS, default='blueberry')
    shared_with = models.ManyToManyField(User, related_name='shared_events', blank=True)