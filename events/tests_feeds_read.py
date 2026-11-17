"""Reading calendar links safely (CO/BE18, part 1): the link check (SSRF),
the download and the .ics reader, tested directly. The web is never really
called here: DNS and requests.get are faked. The helpers are shared with the
API tests in tests_feeds.py."""
import ipaddress
import socket
from datetime import datetime, timezone as dt_timezone
from unittest import mock

import requests
from django.test import SimpleTestCase

from .feeds import FeedError, check_url, fetch, read

UTC = dt_timezone.utc

FAKE_DNS = {
    'example.com': '93.184.216.34',
    'cdn.example.com': '93.184.216.35',
    'localhost': '127.0.0.1',
    'internal.example': '10.0.0.5',  # a public-looking name pointing inside
}


def fake_getaddrinfo(host, *args, **kwargs):
    ip = FAKE_DNS.get(host, host)
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise socket.gaierror('not found')
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, '', (ip, 443))]


class FakeResponse:
    def __init__(self, body=b'', status=200, location=None):
        self.body = body if isinstance(body, bytes) else body.encode()
        self.status_code = status
        self.headers = {'Location': location} if location else {}

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]

    def close(self):
        pass


def vevent(uid, summary, start, end=None, extra=''):
    lines = ['BEGIN:VEVENT']
    if uid:
        lines.append(f'UID:{uid}')
    lines.append(f'SUMMARY:{summary}')
    if start:
        lines.append(start if ':' in start else f'DTSTART:{start}')
    if end:
        lines.append(end if ':' in end else f'DTEND:{end}')
    if extra:
        lines.append(extra)
    lines.append('END:VEVENT')
    return '\r\n'.join(lines) + '\r\n'


def calendar(*events):
    return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n' + ''.join(events) + 'END:VCALENDAR\r\n'


CHELSEA = calendar(
    vevent('match-1', 'Chelsea v Arsenal', '20261120T150000Z', '20261120T170000Z', 'LOCATION:Stamford Bridge'),
    vevent('match-2', 'Liverpool v Chelsea', '20261205T173000Z', '20261205T193000Z'),
)

UNSAFE_OR_BROKEN_LINKS = [
    'http://localhost/c.ics',
    'http://127.0.0.1/c.ics',
    'http://10.0.0.5/c.ics',
    'http://192.168.1.1/c.ics',
    'http://169.254.169.254/latest/meta-data/',  # the cloud's secret address
    'http://[::1]/c.ics',
    'https://internal.example/c.ics',
    'ftp://example.com/c.ics',
    'file:///etc/passwd',
    'https://example.com:22/c.ics',
    'https://user:secret@example.com/c.ics',
    'https://nowhere.invalid/c.ics',  # the name doesn't exist
    'not a link',
    '',
]


class FakeWebMixin:
    """Fakes DNS and requests.get for each test."""

    def setUp(self):
        super().setUp()
        dns = mock.patch('events.feeds.socket.getaddrinfo', side_effect=fake_getaddrinfo)
        dns.start()
        self.addCleanup(dns.stop)
        get = mock.patch('events.feeds.requests.get', return_value=FakeResponse(CHELSEA))
        self.get = get.start()
        self.addCleanup(get.stop)

    def serve(self, *responses):
        self.get.side_effect = list(responses)


class CheckUrlTests(FakeWebMixin, SimpleTestCase):
    """SSRF: the server must only ever visit normal public websites."""

    def test_a_normal_link_is_fine(self):
        self.assertEqual(check_url(' https://example.com/c.ics '), 'https://example.com/c.ics')

    def test_webcal_becomes_https(self):
        self.assertEqual(check_url('webcal://example.com/c.ics'), 'https://example.com/c.ics')
        self.assertEqual(check_url('WEBCAL://example.com/c.ics'), 'https://example.com/c.ics')

    def test_unsafe_or_broken_links_are_refused(self):
        for url in UNSAFE_OR_BROKEN_LINKS:
            with self.subTest(url=url), self.assertRaises(FeedError):
                check_url(url)


class FetchTests(FakeWebMixin, SimpleTestCase):
    def test_returns_the_file(self):
        self.assertEqual(fetch('https://example.com/c.ics'), CHELSEA.encode())

    def test_never_lets_requests_follow_redirects_and_always_times_out(self):
        fetch('https://example.com/c.ics')
        self.assertIs(self.get.call_args.kwargs['allow_redirects'], False)
        self.assertTrue(self.get.call_args.kwargs['timeout'])

    def test_an_unsafe_link_is_never_requested(self):
        with self.assertRaises(FeedError):
            fetch('http://169.254.169.254/latest/meta-data/')
        self.get.assert_not_called()

    def test_a_redirect_to_a_private_address_is_blocked(self):
        self.serve(FakeResponse(status=302, location='http://169.254.169.254/latest/'))
        with self.assertRaises(FeedError):
            fetch('https://example.com/c.ics')
        self.assertEqual(self.get.call_count, 1)

    def test_a_redirect_to_a_public_address_is_followed(self):
        self.serve(FakeResponse(status=301, location='https://cdn.example.com/c.ics'), FakeResponse(CHELSEA))
        self.assertEqual(fetch('https://example.com/c.ics'), CHELSEA.encode())
        self.assertEqual(self.get.call_args.args[0], 'https://cdn.example.com/c.ics')

    def test_a_relative_redirect_is_followed(self):
        self.serve(FakeResponse(status=302, location='/new.ics'), FakeResponse(CHELSEA))
        fetch('https://example.com/c.ics')
        self.assertEqual(self.get.call_args.args[0], 'https://example.com/new.ics')

    def test_too_many_redirects_are_refused(self):
        self.serve(*[FakeResponse(status=302, location=f'https://example.com/{n}') for n in range(5)])
        with self.assertRaises(FeedError):
            fetch('https://example.com/c.ics')
        self.assertEqual(self.get.call_count, 4)

    def test_site_problems_give_a_clear_error(self):
        for problem, message in [
            (FakeResponse(status=404), 'error (404)'),
            (requests.Timeout(), 'too long'),
            (requests.ConnectionError(), "Couldn't reach"),
            (FakeResponse(b'x' * (2 * 1024 * 1024 + 1)), 'too big'),
        ]:
            with self.subTest(problem=problem):
                self.serve(problem)
                with self.assertRaisesMessage(FeedError, message):
                    fetch('https://example.com/c.ics')


class ReadTests(SimpleTestCase):
    def test_reads_the_events(self):
        events = read(CHELSEA.encode())
        self.assertEqual(set(events), {'match-1', 'match-2'})
        self.assertEqual(events['match-1'], {
            'title': 'Chelsea v Arsenal', 'location': 'Stamford Bridge', 'description': '',
            'start': datetime(2026, 11, 20, 15, tzinfo=UTC), 'end': datetime(2026, 11, 20, 17, tzinfo=UTC),
        })

    def test_all_day_time_zone_and_missing_ends(self):
        events = read(calendar(
            vevent('a', 'Cup draw', 'DTSTART;VALUE=DATE:20261125'),
            vevent('b', 'Away game', 'DTSTART;TZID=Europe/London:20261212T150000',
                   'DTEND;TZID=Europe/London:20261212T170000'),
            vevent('c', 'No end', '20261213T150000Z'),
            vevent('d', 'Duration', '20261214T150000Z', extra='DURATION:PT90M'),
            vevent('e', 'Floating', '20261215T090000'),
        ).encode())
        # All day = local midnight to the next midnight (Bogota is UTC-5).
        self.assertEqual(events['a']['start'], datetime(2026, 11, 25, 5, tzinfo=UTC))
        self.assertEqual(events['a']['end'], datetime(2026, 11, 26, 5, tzinfo=UTC))
        self.assertEqual(events['b']['start'], datetime(2026, 12, 12, 15, tzinfo=UTC))
        self.assertEqual(events['c']['end'], datetime(2026, 12, 13, 16, tzinfo=UTC))
        self.assertEqual(events['d']['end'], datetime(2026, 12, 14, 16, 30, tzinfo=UTC))
        # A time with no zone is local time.
        self.assertEqual(events['e']['start'], datetime(2026, 12, 15, 14, tzinfo=UTC))

    def test_broken_old_and_long_events(self):
        events = read(calendar(
            vevent(None, 'No UID', '20261120T150000Z'),
            vevent('no-start', 'No start', None),
            vevent('old', 'Last season', '20240101T150000Z', '20240101T170000Z'),
            vevent('long', 'x' * 300, '20261120T150000Z', '20261120T170000Z'),
            vevent('untitled', '', '20261120T150000Z'),
        ).encode())
        self.assertEqual(set(events), {'long', 'untitled'})
        self.assertEqual(len(events['long']['title']), 200)
        self.assertEqual(events['untitled']['title'], 'Untitled')

    def test_not_a_calendar(self):
        for data in [b'<html>hello</html>', b'']:
            with self.subTest(data=data), self.assertRaisesMessage(FeedError, "isn't a calendar"):
                read(data)

    def test_more_than_2000_events_is_refused(self):
        many = calendar(*[vevent(f'e{n}', 'Game', '20261120T150000Z') for n in range(2001)])
        with self.assertRaisesMessage(FeedError, 'more than 2000'):
            read(many.encode())
