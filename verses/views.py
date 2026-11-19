from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .bible_gateway import VerseUnavailable, fetch_votd
from .models import DailyVerse
from .serializers import DailyVerseSerializer

# After Bible Gateway fails, wait this long before asking again, so an outage
# isn't hit by every request.
RETRY_AFTER = 10 * 60  # seconds
FAILED_KEY = 'verses:bible-gateway-failed'


def today():
    return timezone.localdate()  # Bogota


def _todays_verse(day):
    """Today's saved verse, or fetch and save it (once a day). None if
    Bible Gateway can't give it right now."""
    verse = DailyVerse.objects.filter(date=day).first()
    if verse or cache.get(FAILED_KEY):
        return verse
    try:
        fields = fetch_votd()
    except VerseUnavailable:
        cache.set(FAILED_KEY, True, RETRY_AFTER)
        return None
    try:
        verse, _ = DailyVerse.objects.update_or_create(date=day, defaults=fields)
    except IntegrityError:  # another request saved it at the same moment
        verse = DailyVerse.objects.get(date=day)
    # Keep only one verse: this is a cache, not a collection.
    DailyVerse.objects.exclude(pk=verse.pk).delete()
    return verse


@extend_schema(responses={200: DailyVerseSerializer, 502: None})
@api_view(['GET'])
def verse(request):
    """Bible Gateway's NTV verse of the day, the same for everyone. If Bible
    Gateway is down: the last verse we had (`stale: true`), or 502."""
    day = today()
    daily = _todays_verse(day) or DailyVerse.objects.order_by('-date').first()
    if daily is None:
        return Response({'detail': 'The verse service is unavailable.'}, status=502)
    return Response(DailyVerseSerializer(daily, context={'today': day}).data)
