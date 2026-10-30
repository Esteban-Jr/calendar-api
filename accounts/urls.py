from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('verify/', views.verify, name='verify'),
    path('resend/', views.resend, name='resend'),
    path('forgot/', views.forgot, name='forgot'),
    path('reset/', views.reset, name='reset'),
]
