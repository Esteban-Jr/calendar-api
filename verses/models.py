from django.db import models


class DailyVerse(models.Model):
    """Bible Gateway's NTV verse of the day, kept so we ask them at most once
    a day (CO/BE19). Only the latest one is kept: this is a cache of their
    public verse, never a copy of the Bible."""

    date = models.DateField(unique=True)  # the local (Bogota) day it was fetched for
    text = models.TextField()
    reference = models.CharField(max_length=100)
    version_name = models.CharField(max_length=100)
    link = models.URLField(max_length=500)
    copyright_link = models.URLField(max_length=500)
    fetched = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.date}: {self.reference}'
