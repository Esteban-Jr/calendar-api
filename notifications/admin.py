from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'kind', 'actor', 'event_title', 'read', 'created']
    list_filter = ['kind', 'read']
