"""Calendar links API (CO/BE18, part 2): add an .ics / webcal link, its
events show in my calendar, read-only. The link check, download and reader
are tested on their own in tests_feeds_read.py; here the web is faked the
same way."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from .models import Event, Feed
from .tests_feeds_read import FakeResponse, FakeWebMixin


class FeedTestCase(FakeWebMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.client.force_authenticate(user=self.anna)

    def add(self, url='https://example.com/chelsea.ics', name='Chelsea', **extra):
        return self.client.post('/api/feeds/', {'url': url, 'name': name, **extra}, format='json')

    def titles(self, url='/api/events/'):
        return sorted(event['title'] for event in self.client.get(url).data)


class AddingALinkTests(FeedTestCase):
    def test_adding_a_link_imports_its_events(self):
        response = self.add(color='mint')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['event_count'], 2)
        self.assertEqual(response.data['last_error'], '')
        self.assertIsNotNone(response.data['last_fetched'])
        events = self.client.get('/api/events/').data
        self.assertEqual(sorted(e['title'] for e in events), ['Chelsea v Arsenal', 'Liverpool v Chelsea'])
        match = next(e for e in events if e['title'] == 'Chelsea v Arsenal')
        self.assertEqual(match['imported_from'], {'id': response.data['id'], 'name': 'Chelsea'})
        self.assertEqual(match['location'], 'Stamford Bridge')
        self.assertEqual(match['start'], '2026-11-20T10:00:00-05:00')
        self.assertEqual(match['color'], 'mint')
        self.assertIsNone(match['reminder'])

    def test_webcal_links_are_fetched_over_https(self):
        response = self.add(url='webcal://example.com/chelsea.ics')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['url'], 'https://example.com/chelsea.ics')
        self.assertEqual(self.get.call_args.args[0], 'https://example.com/chelsea.ics')

    def test_my_own_events_are_not_marked_imported(self):
        self.client.post('/api/events/', {
            'title': 'Dentist', 'start': '2026-11-21T09:00:00Z', 'end': '2026-11-21T10:00:00Z',
        }, format='json')
        self.add()
        dentist = next(e for e in self.client.get('/api/events/').data if e['title'] == 'Dentist')
        self.assertIsNone(dentist['imported_from'])

    def test_needs_a_name_and_a_link(self):
        response = self.client.post('/api/feeds/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.data)
        self.assertIn('url', response.data)

    def test_the_same_link_twice_gives_400(self):
        self.add()
        response = self.add(url='webcal://example.com/chelsea.ics')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feed.objects.count(), 1)

    def test_an_eleventh_link_gives_400(self):
        for n in range(10):
            self.assertEqual(self.add(url=f'https://example.com/{n}.ics').status_code, 201)
        response = self.add(url='https://example.com/11.ics')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feed.objects.count(), 10)

    def test_needs_a_login(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/feeds/').status_code, 401)
        self.assertEqual(self.add().status_code, 401)


class BadLinkTests(FeedTestCase):
    """The details are in tests_feeds_read.py; here: the API answers 400,
    says why under `url`, and saves nothing."""

    def test_an_unsafe_link_gives_400_and_is_never_fetched(self):
        for url in ['http://127.0.0.1/c.ics', 'http://169.254.169.254/latest/meta-data/', 'ftp://example.com/c.ics']:
            with self.subTest(url=url):
                response = self.add(url=url)
                self.assertEqual(response.status_code, 400)
                self.assertIn('url', response.data)
        self.get.assert_not_called()
        self.assertEqual(Feed.objects.count(), 0)

    def test_a_link_that_cannot_be_read_gives_400(self):
        for problem in [FakeResponse(status=404), FakeResponse('<html>hello</html>')]:
            with self.subTest(problem=problem):
                self.serve(problem)
                response = self.add()
                self.assertEqual(response.status_code, 400)
                self.assertIn('url', response.data)
        self.assertEqual(Feed.objects.count(), 0)


class ImportedEventTests(FeedTestCase):
    def setUp(self):
        super().setUp()
        self.feed_id = self.add().data['id']
        self.match = Event.objects.get(feed_uid='match-1')

    def test_imported_events_follow_the_date_filter(self):
        url = '/api/events/?start=2026-11-01T00:00:00Z&end=2026-11-30T23:59:59Z'
        self.assertEqual(self.titles(url), ['Chelsea v Arsenal'])

    def test_imported_events_cannot_be_changed_or_deleted(self):
        url = f'/api/events/{self.match.id}/'
        self.assertEqual(self.client.patch(url, {'title': 'Mine now'}, format='json').status_code, 403)
        self.assertEqual(self.client.put(url, {
            'title': 'Mine now', 'start': '2026-11-20T15:00:00Z', 'end': '2026-11-20T17:00:00Z',
        }, format='json').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.match.refresh_from_db()
        self.assertEqual(self.match.title, 'Chelsea v Arsenal')

    def test_deleting_the_link_removes_its_events(self):
        response = self.client.delete(f'/api/feeds/{self.feed_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Event.objects.count(), 0)

    def test_renaming_and_recolouring_a_link(self):
        response = self.client.patch(f'/api/feeds/{self.feed_id}/', {
            'name': 'Blues', 'color': 'strawberry', 'url': 'https://example.com/other.ics',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Blues')
        self.assertEqual(response.data['url'], 'https://example.com/chelsea.ics')  # the link can't change
        self.match.refresh_from_db()
        self.assertEqual(self.match.color, 'strawberry')

    def test_my_links_list(self):
        response = self.client.get('/api/feeds/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([feed['name'] for feed in response.data], ['Chelsea'])
        self.assertEqual(response.data[0]['event_count'], 2)

    def test_other_peoples_links_are_hidden(self):
        self.client.force_authenticate(user=self.ben)
        self.assertEqual(self.client.get('/api/feeds/').data, [])
        self.assertEqual(self.client.get(f'/api/feeds/{self.feed_id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/feeds/{self.feed_id}/').status_code, 404)
        self.assertEqual(self.titles(), [])

