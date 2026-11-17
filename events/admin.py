from django.contrib import admin

from .models import Feed


@admin.register(Feed)
class FeedAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'url', 'last_fetched', 'last_error']
    search_fields = ['name', 'url', 'owner__username']
