from django.db import models
from django.contrib.auth.models import User

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    reminder = models.PositiveIntegerField(null=True, blank=True)
    shared_with = models.ManyToManyField(User, related_name='shared_events', blank=True)