from django.urls import path

from .views import verse

urlpatterns = [
    path('verse/', verse, name='verse'),
]
