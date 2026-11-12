from django.urls import path
from .views import mark_read, notification_list

urlpatterns = [
    path('notifications/', notification_list, name='notifications'),
    path('notifications/read/', mark_read, name='notifications-read'),
]
