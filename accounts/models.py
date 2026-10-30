from django.contrib.auth.models import User
from django.db import models


class PendingSignup(models.Model):
    """Someone who asked to create an account but has not entered the emailed code yet.

    The real User is only created once the code is confirmed, so an abandoned
    sign-up leaves nothing behind except this row.
    """
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150)
    password_hash = models.CharField(max_length=128)  # already hashed, never the plain password
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.username} <{self.email}>'


class ResetCode(models.Model):
    """The emailed code that lets a user choose a new password."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'reset code for {self.user.username}'
