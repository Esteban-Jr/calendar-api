"""GET /api/verse/ (CO/BE19): Bible Gateway's NTV verse of the day, asked
for at most once a day and shared by everyone. Bible Gateway is faked here."""
from datetime import date, timedelta
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import DailyVerse

TODAY = date(2026, 11, 16)

# What Bible Gateway really sends (16/11/26), HTML entities and all.
VOTD = {
    'votd': {
        'text': '&ldquo;Abre mis ojos, para que vea las verdades maravillosas que hay en tus ense&#241;anzas.&rdquo;',
        'rawtext': 'Abre mis ojos, para que vea las verdades maravillosas que hay en tus enseñanzas.',
        'display_ref': 'Salmos 119:18',
        'reference': 'Psalm 119:18',
        'permalink': 'https://www.biblegateway.com/passage/?search=Psalm%20119%3A18&amp;version=NTV',
        'copyrightlink': 'https://www.biblegateway.com/versions/index.php?action=getVersionInfo&amp;vid=159&amp;lang=2',
        'version': 'Nueva Traducci&#243;n Viviente',
        'version_id': 'NTV',
    },
}


def answer(data=VOTD, status=200):
    response = mock.Mock(status_code=status)
    if isinstance(data, Exception):
        response.json.side_effect = data
    else:
        response.json.return_value = data
    return response


class VerseTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client.force_authenticate(user=User.objects.create_user('anna', password='pass12345'))
        get = mock.patch('verses.bible_gateway.requests.get', return_value=answer())
        self.get = get.start()
        self.addCleanup(get.stop)
        today = mock.patch('verses.views.today', return_value=TODAY)
        self.today = today.start()
        self.addCleanup(today.stop)

    def verse(self):
        return self.client.get('/api/verse/')

    def save_old_verse(self):
        DailyVerse.objects.create(
            date=TODAY - timedelta(days=1), text='Old verse', reference='Juan 3:16',
            version_name='Nueva Traducción Viviente', link='https://www.biblegateway.com/passage/?search=John+3%3A16',
            copyright_link='https://www.biblegateway.com/versions/',
        )

    def test_returns_todays_verse_tidied(self):
        response = self.verse()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'date': '2026-11-16',
            'text': 'Abre mis ojos, para que vea las verdades maravillosas que hay en tus enseñanzas.',
            'reference': 'Salmos 119:18',
            'version': 'NTV',
            'version_name': 'Nueva Traducción Viviente',
            'link': 'https://www.biblegateway.com/passage/?search=Psalm%20119%3A18&version=NTV',
            'copyright_link': 'https://www.biblegateway.com/versions/index.php?action=getVersionInfo&vid=159&lang=2',
            'stale': False,
        })
        url = self.get.call_args.args[0]
        self.assertIn('biblegateway.com/votd/get/', url)
        self.assertIn('version=NTV', url)
        self.assertTrue(self.get.call_args.kwargs['timeout'])

    def test_asks_bible_gateway_only_once_a_day(self):
        self.verse()
        self.verse()
        self.client.force_authenticate(user=User.objects.create_user('ben', password='pass12345'))
        self.assertEqual(self.verse().data['reference'], 'Salmos 119:18')
        self.assertEqual(self.get.call_count, 1)

    def test_a_new_day_asks_again_and_keeps_only_one_verse(self):
        self.verse()
        self.today.return_value = TODAY + timedelta(days=1)
        response = self.verse()
        self.assertEqual(response.data['date'], '2026-11-17')
        self.assertFalse(response.data['stale'])
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(DailyVerse.objects.count(), 1)

    def test_bible_gateway_down_with_no_saved_verse_gives_502(self):
        for problem in [
            requests.Timeout(),
            requests.ConnectionError(),
            answer(status=500),
            answer(data=ValueError('not JSON')),
            answer(data={'votd': {'rawtext': '   ', 'display_ref': 'Salmos 1:1'}}),
            answer(data={'something': 'else'}),
            answer(data=['a', 'list']),
        ]:
            with self.subTest(problem=problem):
                cache.clear()
                self.get.side_effect = [problem]
                response = self.verse()
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.data, {'detail': 'The verse service is unavailable.'})
        self.assertEqual(DailyVerse.objects.count(), 0)

    def test_bible_gateway_down_gives_the_last_verse_marked_stale(self):
        self.save_old_verse()
        self.get.side_effect = requests.Timeout()
        response = self.verse()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['date'], '2026-11-15')
        self.assertEqual(response.data['text'], 'Old verse')
        self.assertTrue(response.data['stale'])

    def test_waits_10_minutes_after_a_failure_before_asking_again(self):
        self.get.side_effect = requests.Timeout()
        self.verse()
        self.verse()
        self.assertEqual(self.get.call_count, 1)
        cache.clear()  # as if 10 minutes had passed
        self.get.side_effect = None
        self.assertEqual(self.verse().status_code, 200)
        self.assertEqual(self.get.call_count, 2)

    def test_needs_a_login(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.verse().status_code, 401)
        self.get.assert_not_called()
