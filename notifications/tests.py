from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from events.models import Event, Share
from friends.models import Friendship
from push.models import PushSubscription
from .models import Notification


@override_settings(VAPID_PRIVATE_KEY='private', VAPID_SUBJECT='mailto:test@example.com')
@mock.patch('push.send.webpush')
class NotificationTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.cleo = User.objects.create_user('cleo', password='pass12345')
        for friend in [self.ben, self.cleo]:
            Friendship.objects.create(from_user=self.anna, to_user=friend, accepted=True)
        self.dinner = Event.objects.create(
            title='Dinner', start='2026-11-20T19:00:00Z', end='2026-11-20T21:00:00Z', owner=self.anna,
        )
        # Both have already accepted (invites themselves are tested in events/tests_invites.py).
        self.dinner.shared_with.add(self.ben, self.cleo, through_defaults={'status': Share.ACCEPTED})

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def test_leave_takes_only_me_off_and_tells_the_owner(self, webpush):
        PushSubscription.objects.create(user=self.anna, endpoint='https://web.push.apple.com/anna', p256dh='k', auth='a')
        self.as_user(self.ben)
        self.assertEqual(self.client.post(f'/api/events/{self.dinner.id}/leave/').status_code, 204)
        self.assertEqual(list(self.dinner.shared_with.all()), [self.cleo])
        self.assertEqual(self.client.get(f'/api/events/{self.dinner.id}/').status_code, 404)  # gone for ben

        notification = Notification.objects.get(user=self.anna)
        self.assertEqual(notification.message, 'ben removed “Dinner” from their calendar')
        self.assertEqual(webpush.call_count, 1)  # and pushed to anna's phone
        self.assertIn('ben removed', webpush.call_args.kwargs['data'])

    def test_owner_cannot_leave_their_own_event(self, webpush):
        self.as_user(self.anna)
        self.assertEqual(self.client.post(f'/api/events/{self.dinner.id}/leave/').status_code, 400)

    def test_strangers_cannot_leave(self, webpush):
        stranger = User.objects.create_user('dan', password='pass12345')
        self.as_user(stranger)
        self.assertEqual(self.client.post(f'/api/events/{self.dinner.id}/leave/').status_code, 404)

    def test_owner_can_share_again_after_someone_leaves(self, webpush):
        self.as_user(self.ben)
        self.client.post(f'/api/events/{self.dinner.id}/leave/')
        self.as_user(self.anna)
        response = self.client.patch(f'/api/events/{self.dinner.id}/', {'shared_with': ['ben', 'cleo']}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_deleting_tells_everyone_it_was_shared_with(self, webpush):
        self.as_user(self.anna)
        self.assertEqual(self.client.delete(f'/api/events/{self.dinner.id}/').status_code, 204)
        told = Notification.objects.filter(kind=Notification.EVENT_DELETED)
        self.assertEqual(sorted(n.user.username for n in told), ['ben', 'cleo'])
        self.assertEqual(told.first().message, 'anna deleted “Dinner”')
        self.assertFalse(Notification.objects.filter(user=self.anna).exists())

    def test_deleting_an_unshared_event_tells_nobody(self, webpush):
        self.dinner.shared_with.clear()
        self.as_user(self.anna)
        self.client.delete(f'/api/events/{self.dinner.id}/')
        self.assertFalse(Notification.objects.exists())

    def test_list_and_mark_read(self, webpush):
        self.as_user(self.ben)
        self.client.post(f'/api/events/{self.dinner.id}/leave/')
        self.as_user(self.anna)
        data = self.client.get('/api/notifications/').data
        self.assertEqual(data['unread'], 1)
        self.assertEqual(data['notifications'][0]['message'], 'ben removed “Dinner” from their calendar')
        self.assertEqual(data['notifications'][0]['actor'], 'ben')
        self.assertEqual(self.client.post('/api/notifications/read/').status_code, 204)
        self.assertEqual(self.client.get('/api/notifications/').data['unread'], 0)

    def test_you_only_see_your_own_notifications(self, webpush):
        self.as_user(self.ben)
        self.client.post(f'/api/events/{self.dinner.id}/leave/')
        self.assertEqual(self.client.get('/api/notifications/').data['notifications'], [])

    def test_a_push_failure_does_not_stop_the_action(self, webpush):
        webpush.side_effect = ConnectionError('push service down')
        PushSubscription.objects.create(user=self.anna, endpoint='https://web.push.apple.com/anna', p256dh='k', auth='a')
        self.as_user(self.ben)
        self.assertEqual(self.client.post(f'/api/events/{self.dinner.id}/leave/').status_code, 204)
        self.assertTrue(Notification.objects.filter(user=self.anna).exists())

    def test_needs_a_token(self, webpush):
        self.assertEqual(self.client.get('/api/notifications/').status_code, 401)
