"""Reading calendar links (.ics / webcal) for CO/BE18. import_events saves
them as the link's events.

The links come from users, so the server must only ever visit normal public
websites (no localhost, no private network, no cloud metadata address). That
is checked before every request, including each redirect, which we follow by
hand instead of letting requests do it.

Known gap: DNS rebinding (a name that resolves to a public address when we
check and a private one a moment later when we connect). Narrow, noted in the
PR.
"""
import ipaddress
import socket
from datetime import datetime, time, timedelta
from urllib.parse import urljoin, urlsplit

import requests
from django.db import transaction
from django.utils import timezone
from icalendar import Calendar

from .models import Event

TIMEOUT = 10  # seconds
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_EVENTS = 2000
KEEP_PAST = timedelta(days=365)


class FeedError(Exception):
    """Something wrong with a link or what it returned. The message is safe
    to show to the user."""


def check_url(url):
    """Return the link as https/http, or raise FeedError if it's not a normal
    public web address."""
    url = (url or '').strip()
    if url.lower().startswith('webcal://'):
        url = 'https://' + url[len('webcal://'):]
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FeedError('Enter a valid calendar link.')
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise FeedError('Enter a web link starting with https://, http:// or webcal://.')
    if parts.username or parts.password:
        raise FeedError('Links with a username or password are not allowed.')
    if port not in (None, 80, 443):
        raise FeedError('Only normal web ports (80 and 443) are allowed.')
    try:
        addresses = socket.getaddrinfo(parts.hostname, port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise FeedError("Couldn't find that website.")
    for *_, sockaddr in addresses:
        ip = ipaddress.ip_address(sockaddr[0].split('%')[0])
        if not ip.is_global or ip.is_multicast:
            raise FeedError('That link points to a private address, which is not allowed.')
    return url


def fetch(url):
    """Download a calendar link safely and return its bytes."""
    for _ in range(MAX_REDIRECTS + 1):
        url = check_url(url)
        try:
            response = requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.Timeout:
            raise FeedError('The calendar website took too long to answer.')
        except requests.RequestException:
            raise FeedError("Couldn't reach the calendar website.")
        try:
            if response.status_code in (301, 302, 303, 307, 308) and response.headers.get('Location'):
                url = urljoin(url, response.headers['Location'])
                continue
            if response.status_code != 200:
                raise FeedError(f'The calendar website answered with an error ({response.status_code}).')
            body = b''
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body += chunk
                if len(body) > MAX_BYTES:
                    raise FeedError('That calendar is too big (over 2 MB).')
            return body
        finally:
            response.close()
    raise FeedError('That link redirects too many times.')


def _as_datetime(value):
    """An .ics date or time as an aware datetime. All-day dates and times
    without a zone are in the calendar's own time zone."""
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    return timezone.make_aware(datetime.combine(value, time.min))


def read(data):
    """The events in an .ics file, as dicts ready for Event fields."""
    try:
        calendar = Calendar.from_ical(data)
    except ValueError:
        raise FeedError("That link isn't a calendar (.ics) file.")
    oldest = timezone.now() - KEEP_PAST
    events = {}
    for item in calendar.walk('VEVENT'):
        uid = str(item.get('UID', '')).strip()[:255]
        start = item.get('DTSTART')
        if not uid or start is None:
            continue
        all_day = not isinstance(start.dt, datetime)
        start = _as_datetime(start.dt)
        if item.get('DTEND') is not None:
            end = _as_datetime(item['DTEND'].dt)
        elif item.get('DURATION') is not None:
            end = start + item['DURATION'].dt
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        if end <= start:
            end = start + timedelta(hours=1)
        if end < oldest:
            continue
        events[uid] = {
            'title': str(item.get('SUMMARY', '')).strip()[:200] or 'Untitled',
            'location': str(item.get('LOCATION', '')).strip()[:200],
            'description': str(item.get('DESCRIPTION', '')).strip(),
            'start': start,
            'end': end,
        }
        if len(events) > MAX_EVENTS:
            raise FeedError(f'That calendar has more than {MAX_EVENTS} events.')
    return events


def import_events(feed, events):
    """Make the feed's saved events match `events` (by UID): add, update, remove."""
    with transaction.atomic():
        saved = {event.feed_uid: event for event in feed.events.all()}
        for uid, fields in events.items():
            event = saved.pop(uid, None) or Event(feed=feed, feed_uid=uid, owner=feed.owner)
            for name, value in fields.items():
                setattr(event, name, value)
            event.color = feed.color
            event.save()
        Event.objects.filter(pk__in=[event.pk for event in saved.values()]).delete()
