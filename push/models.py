from django.contrib.auth.models import User
from django.db import models


class PushSubscription(models.Model):
    """One device (phone or browser) that has turned on notifications. The
    endpoint is the address its push service (Apple, Google, Mozilla...) gave
    it; p256dh and auth are the keys used to encrypt messages for it."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} on {self.endpoint[:40]}…'
