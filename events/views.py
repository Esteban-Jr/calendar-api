from rest_framework import viewsets, permissions
from .models import Event
from .serializers import EventSerializer
from django.db.models import Q
from .permissions import IsOwnerOrReadOnly
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response

class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        qs = Event.objects.filter(
            Q(owner=self.request.user) | Q(shared_with=self.request.user)
        ).distinct()
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            qs = qs.filter(end__gte=start)
        if end:
            qs = qs.filter(start__lte=end)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

@api_view(['GET'])
def me(request):
    return Response({'id': request.user.id, 'username': request.user.username})


@api_view(['GET'])
def holidays(request):
    year = request.query_params.get('year')
    if not year:
        return Response({'detail': 'year is required'}, status=400)
    if not year.isdigit():
        return Response({'detail': 'year must be a number'}, status=400)

    url = f'https://date.nager.at/api/v3/PublicHolidays/{year}/CO'
    try:
        r = requests.get(url, timeout=5)
    except requests.RequestException:
        return Response({'detail': 'Holiday service unavailable'}, status=502)

    if r.status_code != 200:
        return Response({'detail': 'Could not get holidays'}, status=502)

    result = [
        {'date': h['date'], 'title': h['localName'], 'name': h['name']}
        for h in r.json()
    ]
    return Response(result)