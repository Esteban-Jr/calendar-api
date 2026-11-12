from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class Friendship(models.Model):
    """A friend request from one person to another. Once the other person
    accepts it, the two are friends (in both directions)."""

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_sent')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_received')
    accepted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_user', 'to_user'], name='one_request_per_pair'),
            models.CheckConstraint(condition=~Q(from_user=models.F('to_user')), name='no_friending_yourself'),
        ]

    def __str__(self):
        state = 'friends' if self.accepted else 'requested'
        return f'{self.from_user} → {self.to_user} ({state})'

    def other(self, user):
        """The person on the other side of this friendship from `user`."""
        return self.to_user if self.from_user == user else self.from_user


def between(a, b):
    """Any request between a and b, whichever of them sent it."""
    return Friendship.objects.filter(Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a))


def friends_of(user):
    """Users who are accepted friends of `user`."""
    return User.objects.filter(
        Q(friend_requests_sent__to_user=user, friend_requests_sent__accepted=True)
        | Q(friend_requests_received__from_user=user, friend_requests_received__accepted=True)
    ).distinct()
