from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from friends.models import Friendship
from .models import Event

class EventTests(APITestCase):
    def test_no_token_gives_401(self):
        response = self.client.get('/api/events/')
        self.assertEqual(response.status_code, 401)

    def test_end_before_start_gives_400(self):
        user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/events/', {
            'title': 'Bad',
            'start': '2026-10-31T09:00:00Z',
            'end': '2026-10-31T08:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_other_user_cannot_see_event(self):
        anna = User.objects.create_user('anna', password='pass12345')
        ben = User.objects.create_user('ben', password='pass12345')
        event = Event.objects.create(
            title='Private Event',
            start='2026-10-31T09:00:00Z',
            end='2026-10-31T10:00:00Z',
            owner=anna
        )
        self.client.force_authenticate(user=ben)
        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.status_code, 404)

    def test_shared_user_cannot_delete_event(self):
        anna = User.objects.create_user('anna', password='pass12345')
        ben = User.objects.create_user('ben', password='pass12345')
        event = Event.objects.create(
            title='Shared Event',
            start='2026-10-31T09:00:00Z',
            end='2026-10-31T10:00:00Z',
            owner=anna
        )
        event.shared_with.add(ben)
        self.client.force_authenticate(user=ben)
        response = self.client.delete(f'/api/events/{event.id}/')
        self.assertEqual(response.status_code, 403)

    def test_color_defaults_to_blueberry(self):
        user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/events/', {
            'title': 'Plain',
            'start': '2026-10-31T09:00:00Z',
            'end': '2026-10-31T10:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['color'], 'blueberry')

    def test_unknown_color_gives_400(self):
        user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/events/', {
            'title': 'Odd',
            'start': '2026-10-31T09:00:00Z',
            'end': '2026-10-31T10:00:00Z',
            'color': 'neon',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_me_needs_a_token(self):
        self.assertEqual(self.client.get('/api/me/').status_code, 401)

    def test_me_returns_the_logged_in_user(self):
        user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['id'], response.data['username']), (user.id, 'anna'))  # more in accounts/tests_me.py

    def test_owner_can_share_by_username(self):
        anna = User.objects.create_user('anna', password='pass12345')
        ben = User.objects.create_user('ben', password='pass12345')
        Friendship.objects.create(from_user=anna, to_user=ben, accepted=True)  # sharing needs friends
        event = Event.objects.create(
            title='Plan', start='2026-10-31T09:00:00Z', end='2026-10-31T10:00:00Z', owner=anna,
        )
        self.client.force_authenticate(user=anna)
        response = self.client.patch(f'/api/events/{event.id}/', {'shared_with': ['ben']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['shared_with'], ['ben'])
        self.assertEqual(response.data['owner_username'], 'anna')
        # Ben now sees it, and sees who it came from.
        self.client.force_authenticate(user=ben)
        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['owner_username'], 'anna')

    def test_sharing_with_unknown_username_gives_400(self):
        anna = User.objects.create_user('anna', password='pass12345')
        event = Event.objects.create(
            title='Plan', start='2026-10-31T09:00:00Z', end='2026-10-31T10:00:00Z', owner=anna,
        )
        self.client.force_authenticate(user=anna)
        response = self.client.patch(f'/api/events/{event.id}/', {'shared_with': ['nobody']}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_shared_user_cannot_change_who_it_is_shared_with(self):
        anna = User.objects.create_user('anna', password='pass12345')
        ben = User.objects.create_user('ben', password='pass12345')
        User.objects.create_user('cleo', password='pass12345')
        event = Event.objects.create(
            title='Plan', start='2026-10-31T09:00:00Z', end='2026-10-31T10:00:00Z', owner=anna,
        )
        event.shared_with.add(ben)
        self.client.force_authenticate(user=ben)
        response = self.client.patch(f'/api/events/{event.id}/', {'shared_with': ['ben', 'cleo']}, format='json')
        self.assertEqual(response.status_code, 403)


class EventDateFilterTests(APITestCase):
    """GET /api/events/?start=&end= (CO/BE13): bad dates give a 400 that
    names the parameter; good or missing dates work as before."""

    def setUp(self):
        self.user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=self.user)
        Event.objects.create(title='October', owner=self.user,
                             start='2026-10-10T09:00:00Z', end='2026-10-10T10:00:00Z')
        Event.objects.create(title='November', owner=self.user,
                             start='2026-11-10T09:00:00Z', end='2026-11-10T10:00:00Z')

    def titles(self, response):
        return sorted(event['title'] for event in response.data)

    def test_bad_start_gives_400_naming_start(self):
        response = self.client.get('/api/events/?start=banana')
        self.assertEqual(response.status_code, 400)
        self.assertIn('start', response.data)

    def test_bad_end_gives_400_naming_end(self):
        response = self.client.get('/api/events/?end=banana')
        self.assertEqual(response.status_code, 400)
        self.assertIn('end', response.data)

    def test_impossible_date_gives_400(self):
        response = self.client.get('/api/events/?start=2026-13-01')
        self.assertEqual(response.status_code, 400)
        self.assertIn('start', response.data)

    def test_valid_range_returns_only_overlapping_events(self):
        response = self.client.get('/api/events/?start=2026-11-01T00:00:00Z&end=2026-11-30T23:59:59Z')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ['November'])

    def test_app_format_with_milliseconds_works(self):
        # The app sends Date.toISOString(), e.g. 2026-11-01T00:00:00.000Z
        response = self.client.get('/api/events/?start=2026-11-01T00:00:00.000Z&end=2026-11-30T23:59:59.999Z')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ['November'])

    def test_date_only_works(self):
        response = self.client.get('/api/events/?start=2026-11-01&end=2026-11-30')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ['November'])

    def test_no_dates_returns_all_events(self):
        response = self.client.get('/api/events/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), ['November', 'October'])


class DateOnlyFilterTests(APITestCase):
    """GET /api/events/?start=&end= with a bare date (CO/BE33): a bare `end`
    covers that whole day and a bare `start` begins at midnight, both in the
    server's time (Bogota, UTC-5). Full date-times work as before."""

    def setUp(self):
        self.user = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=self.user)
        # Times are in Bogota (-05:00), so "the 30th" means Bogota's 30th.
        for title, start, end in [
            ('Late on 31 Oct', '2026-10-31T23:00:00-05:00', '2026-10-31T23:30:00-05:00'),
            ('Just after midnight 1 Nov', '2026-11-01T00:30:00-05:00', '2026-11-01T01:00:00-05:00'),
            ('Afternoon 30 Nov', '2026-11-30T15:00:00-05:00', '2026-11-30T16:00:00-05:00'),
            ('Morning 1 Dec', '2026-12-01T09:00:00-05:00', '2026-12-01T10:00:00-05:00'),
        ]:
            Event.objects.create(title=title, owner=self.user, start=start, end=end)

    def titles(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return sorted(event['title'] for event in response.data)

    def test_date_only_end_includes_events_on_that_day(self):
        self.assertIn('Afternoon 30 Nov', self.titles('/api/events/?end=2026-11-30'))

    def test_date_only_end_excludes_the_next_day(self):
        self.assertNotIn('Morning 1 Dec', self.titles('/api/events/?end=2026-11-30'))

    def test_full_date_time_end_works_as_before(self):
        # Midnight at the start of the 30th, written out in full: the 30th is left out.
        self.assertNotIn('Afternoon 30 Nov', self.titles('/api/events/?end=2026-11-30T00:00:00-05:00'))

    def test_date_only_start_means_start_of_that_day(self):
        titles = self.titles('/api/events/?start=2026-11-01')
        self.assertNotIn('Late on 31 Oct', titles)
        self.assertIn('Just after midnight 1 Nov', titles)

    def test_date_only_range_covers_both_whole_days(self):
        self.assertEqual(self.titles('/api/events/?start=2026-11-01&end=2026-11-30'),
                         ['Afternoon 30 Nov', 'Just after midnight 1 Nov'])

    def test_impossible_date_only_end_gives_400(self):
        response = self.client.get('/api/events/?end=2026-13-01')
        self.assertEqual(response.status_code, 400)
        self.assertIn('end', response.data)
