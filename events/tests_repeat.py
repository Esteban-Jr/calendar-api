"""The repeat rule on events (CO/BE17): saved, returned and checked. Showing
each repeat in the list is #25; reminders for each repeat are #26."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from .models import Event, Share


class RepeatRuleTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.client.force_authenticate(user=self.anna)

    def create(self, start='2026-11-16T09:00:00Z', end='2026-11-16T10:00:00Z', **extra):
        data = {'title': 'Gym', 'start': start, 'end': end, **extra}
        return self.client.post('/api/events/', data, format='json')

    def test_new_events_do_not_repeat(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['repeat'], 'none')
        self.assertIsNone(response.data['repeat_until'])

    def test_create_a_weekly_event_until_a_date(self):
        response = self.create(repeat='weekly', repeat_until='2026-12-31')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['repeat'], 'weekly')
        self.assertEqual(response.data['repeat_until'], '2026-12-31')

    def test_repeat_forever_when_no_until(self):
        response = self.create(repeat='yearly')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data['repeat_until'])

    def test_patch_changes_the_rule(self):
        event_id = self.create(repeat='weekly').data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'repeat': 'monthly'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['repeat'], 'monthly')

    def test_patch_can_clear_until(self):
        event_id = self.create(repeat='daily', repeat_until='2026-11-30').data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'repeat_until': None}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['repeat_until'])

    def test_stopping_the_repeat_with_until_left_over_gives_400(self):
        event_id = self.create(repeat='daily', repeat_until='2026-11-30').data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'repeat': 'none'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('repeat_until', response.data)

    def test_unknown_repeat_gives_400(self):
        response = self.create(repeat='fortnightly')
        self.assertEqual(response.status_code, 400)
        self.assertIn('repeat', response.data)

    def test_until_before_the_start_gives_400(self):
        response = self.create(repeat='weekly', repeat_until='2026-11-15')
        self.assertEqual(response.status_code, 400)
        self.assertIn('repeat_until', response.data)

    def test_until_on_the_start_day_is_fine(self):
        response = self.create(repeat='daily', repeat_until='2026-11-16')
        self.assertEqual(response.status_code, 201)

    def test_until_without_a_repeat_gives_400(self):
        response = self.create(repeat_until='2026-12-31')
        self.assertEqual(response.status_code, 400)
        self.assertIn('repeat_until', response.data)

    def test_event_longer_than_its_repeat_gap_gives_400(self):
        # A 2-day event repeating every day would overlap itself.
        response = self.create(end='2026-11-18T10:00:00Z', repeat='daily')
        self.assertEqual(response.status_code, 400)
        self.assertIn('repeat', response.data)

    def test_long_event_is_fine_with_a_longer_gap(self):
        response = self.create(end='2026-11-18T10:00:00Z', repeat='weekly')
        self.assertEqual(response.status_code, 201)

    def test_moving_the_end_too_far_for_the_rule_gives_400(self):
        event_id = self.create(repeat='daily').data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'end': '2026-11-18T10:00:00Z'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_old_events_do_not_repeat(self):
        event = Event.objects.create(
            title='Old', start='2026-10-01T09:00:00Z', end='2026-10-01T10:00:00Z', owner=self.anna,
        )
        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.data['repeat'], 'none')

    def test_a_friend_sees_the_rule_on_a_shared_event(self):
        event = Event.objects.create(
            title='Gym', start='2026-11-16T09:00:00Z', end='2026-11-16T10:00:00Z', owner=self.anna,
            repeat='weekly',
        )
        Share.objects.create(event=event, user=self.ben, status=Share.ACCEPTED)
        self.client.force_authenticate(user=self.ben)
        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.data['repeat'], 'weekly')
