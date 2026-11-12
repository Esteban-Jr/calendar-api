import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from pywebpush import WebPushException
from rest_framework.test import APITestCase

from events.models import Event
from friends.models import Friendship
from .models import PushSubscription

APPLE = 'https://web.push.apple.com/QGuQyavXutnMHRp6u2y4IjD'


def subscription(endpoint=APPLE):
    return {'endpoint': endpoint, 'keys': {'p256dh': 'BKey', 'auth': 'secret'}}


class PushApiTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.client.force_authenticate(user=self.anna)

    def test_key_without_setup_gives_503(self):
        with override_settings(VAPID_PUBLIC_KEY=''):
            self.assertEqual(self.client.get('/api/push/key/').status_code, 503)

    def test_key(self):
        with override_settings(VAPID_PUBLIC_KEY='BPublic'):
            self.assertEqual(self.client.get('/api/push/key/').data, {'key': 'BPublic'})

    def test_subscribe_and_unsubscribe(self):
        self.assertEqual(self.client.post('/api/push/subscribe/', subscription(), format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/push/subscribe/', subscription(), format='json').status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        response = self.client.post('/api/push/unsubscribe/', {'endpoint': APPLE}, format='json')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PushSubscription.objects.exists())

    def test_only_real_push_services_are_accepted(self):
        for endpoint in [
            'http://web.push.apple.com/x',          # not https
            'https://127.0.0.1:8003/api/events/',   # the server itself
            'https://evil.example.com/push',
            'https://push.apple.com.evil.com/x',    # looks similar, isn't
        ]:
            response = self.client.post('/api/push/subscribe/', subscription(endpoint), format='json')
            self.assertEqual(response.status_code, 400, endpoint)
        for endpoint in ['https://fcm.googleapis.com/fcm/send/abc', 'https://updates.push.services.mozilla.com/wpush/v2/abc']:
            response = self.client.post('/api/push/subscribe/', subscription(endpoint), format='json')
            self.assertEqual(response.status_code, 201, endpoint)

    def test_a_device_moves_to_whoever_signs_in(self):
        ben = User.objects.create_user('ben', password='pass12345')
        self.client.post('/api/push/subscribe/', subscription(), format='json')
        self.client.force_authenticate(user=ben)
        self.client.post('/api/push/subscribe/', subscription(), format='json')
        self.assertEqual(PushSubscription.objects.get().user, ben)

    def test_cannot_unsubscribe_someone_elses_device(self):
        ben = User.objects.create_user('ben', password='pass12345')
        PushSubscription.objects.create(user=ben, endpoint=APPLE, p256dh='k', auth='a')
        self.client.post('/api/push/unsubscribe/', {'endpoint': APPLE}, format='json')
        self.assertTrue(PushSubscription.objects.exists())

    def test_needs_a_token(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post('/api/push/subscribe/', subscription(), format='json').status_code, 401)


@override_settings(VAPID_PRIVATE_KEY='private', VAPID_SUBJECT='mailto:test@example.com')
@mock.patch('push.send.webpush')
class SendRemindersTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        PushSubscription.objects.create(user=self.anna, endpoint=APPLE, p256dh='k', auth='a')

    def event(self, starts_in, reminder, **extra):
        start = timezone.now() + starts_in
        return Event.objects.create(title='Dentist', start=start, end=start + timedelta(hours=1),
                                    owner=self.anna, reminder=reminder, **extra)

    def sent(self, webpush):
        return [json.loads(call.kwargs['data']) for call in webpush.call_args_list]

    def test_sends_a_due_reminder_once(self, webpush):
        event = self.event(timedelta(minutes=10), reminder=30, location='Clinic')
        call_command('send_reminders')
        messages = self.sent(webpush)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['title'], 'Dentist')
        self.assertIn('Starts in 10 min', messages[0]['body'])
        self.assertIn('Clinic', messages[0]['body'])
        self.assertTrue(messages[0]['tag'].startswith(f'{event.id}|'))
        self.assertTrue(messages[0]['tag'].endswith('|30'))
        call_command('send_reminders')
        self.assertEqual(webpush.call_count, 1)  # not again

    def test_not_before_its_time(self, webpush):
        self.event(timedelta(hours=2), reminder=30)
        call_command('send_reminders')
        webpush.assert_not_called()

    def test_not_long_after_the_start(self, webpush):
        self.event(-timedelta(minutes=20), reminder=0)
        call_command('send_reminders')
        webpush.assert_not_called()

    def test_reminds_again_when_the_event_moves(self, webpush):
        event = self.event(timedelta(minutes=5), reminder=10)
        call_command('send_reminders')
        event.start += timedelta(minutes=2)
        event.end += timedelta(minutes=2)
        event.save()
        call_command('send_reminders')
        self.assertEqual(webpush.call_count, 2)

    def test_only_the_owner_is_reminded(self, webpush):
        ben = User.objects.create_user('ben', password='pass12345')
        PushSubscription.objects.create(user=ben, endpoint='https://fcm.googleapis.com/fcm/send/ben', p256dh='k', auth='a')
        Friendship.objects.create(from_user=self.anna, to_user=ben, accepted=True)
        self.event(timedelta(minutes=5), reminder=10).shared_with.add(ben)
        call_command('send_reminders')
        self.assertEqual([c.kwargs['subscription_info']['endpoint'] for c in webpush.call_args_list], [APPLE])

    def test_forgets_devices_that_are_gone(self, webpush):
        webpush.side_effect = WebPushException('Gone', response=mock.Mock(status_code=410))
        self.event(timedelta(minutes=5), reminder=10)
        call_command('send_reminders')
        self.assertFalse(PushSubscription.objects.exists())

    def test_keeps_devices_after_other_errors(self, webpush):
        webpush.side_effect = WebPushException('Busy', response=mock.Mock(status_code=503))
        self.event(timedelta(minutes=5), reminder=10)
        call_command('send_reminders')
        self.assertTrue(PushSubscription.objects.exists())

    def test_events_without_a_reminder_are_ignored(self, webpush):
        self.event(timedelta(minutes=1), reminder=None)
        call_command('send_reminders')
        webpush.assert_not_called()
