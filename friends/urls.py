from django.urls import path
from .views import accept, friends, remove

urlpatterns = [
    path('friends/', friends, name='friends'),
    path('friends/<int:pk>/accept/', accept, name='friend-accept'),
    path('friends/<int:pk>/', remove, name='friend-remove'),
]
