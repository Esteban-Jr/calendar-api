from django.urls import path
from rest_framework.routers import DefaultRouter
from accounts.views import me

from .views import EventViewSet, holidays

router = DefaultRouter()
router.register('events', EventViewSet, basename='event')

urlpatterns = router.urls + [
    path('holidays/', holidays, name='holidays'),
    path('me/', me, name='me'),
]
