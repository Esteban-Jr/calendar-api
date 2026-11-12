from django.urls import path
from .views import public_key, subscribe, unsubscribe

urlpatterns = [
    path('push/key/', public_key, name='push-key'),
    path('push/subscribe/', subscribe, name='push-subscribe'),
    path('push/unsubscribe/', unsubscribe, name='push-unsubscribe'),
]
