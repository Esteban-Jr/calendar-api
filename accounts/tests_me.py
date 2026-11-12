"""/api/me/: who I am, and changing my username (#28)."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from events.models import Event
from friends.models import Friendship
from notifications.models import Notification
from push.models import PushSubscription
from .models import UsernameChange


@override_settings(VAPID_PRIVATE_KEY='private', VAPID_SUBJECT='mailto:test@example.com')
@mock.patch('push.send.webpush')
class MeTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', 'anna@example.com', 'pass12345')
        self.ben = User.objects.create_user('ben', 'ben@example.com', 'pass12345')
        self.client.force_authenticate(user=self.anna)

    def rename(self, username):
        return self.client.patch('/api/me/', {'username': username}, format='json')

    def told(self, user):
        return [n.message for n in Notification.objects.filter(user=user, kind=Notification.USERNAME_CHANGED)]

    def a_week_passes(self):
        UsernameChange.objects.update(changed_at=timezone.now() - timedelta(days=7, minutes=1))

    # ---------- Reading ----------

    def test_get_me(self, webpush):
        data = self.client.get('/api/me/').data
        self.assertEqual(data, {
            'id': self.anna.id, 'username': 'anna', 'email': 'anna@example.com', 'next_username_change': None,
        })

    def test_needs_a_token(self, webpush):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/me/').status_code, 401)
        self.assertEqual(self.rename('x').status_code, 401)

    # ---------- Changing it ----------

    def test_change_my_username(self, webpush):
        response = self.rename('annabel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'annabel')
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.username, 'annabel')
        change = UsernameChange.objects.get()
        self.assertEqual((change.old_username, change.new_username), ('anna', 'annabel'))

    def test_spaces_around_are_ignored(self, webpush):
        self.assertEqual(self.rename('  annabel  ').data['username'], 'annabel')

    def test_same_rules_as_signing_up(self, webpush):
        for bad in ['', 'has space', 'emoji🙂', 'x' * 151]:
            response = self.rename(bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('username', response.data)
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.username, 'anna')

    def test_taken_ignoring_capitals(self, webpush):
        response = self.rename('BEN')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['username'], ['That username is taken.'])

    def test_same_name_is_refused(self, webpush):
        self.assertEqual(self.rename('anna').data['username'], ["That's already your username."])

    def test_my_events_and_shares_follow_the_new_name(self, webpush):
        Friendship.objects.create(from_user=self.anna, to_user=self.ben, accepted=True)
        event = Event.objects.create(title='Dinner', start='2026-11-20T19:00:00Z', end='2026-11-20T21:00:00Z', owner=self.anna)
        event.shared_with.add(self.ben, through_defaults={'status': 'accepted'})
        self.rename('annabel')
        self.client.force_authenticate(user=self.ben)
        shared = self.client.get(f'/api/events/{event.id}/').data
        self.assertEqual(shared['owner_username'], 'annabel')
        friends = self.client.get('/api/friends/').data['friends']
        self.assertEqual([f['username'] for f in friends], ['annabel'])

    def test_i_stay_signed_in_and_log_in_with_the_new_name(self, webpush):
        token = Token.objects.create(user=self.anna)
        self.rename('annabel')
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/me/').data['username'], 'annabel')  # same token still works
        self.client.credentials()
        new = self.client.post('/api-auth/', {'username': 'annabel', 'password': 'pass12345'}, format='json')
        old = self.client.post('/api-auth/', {'username': 'anna', 'password': 'pass12345'}, format='json')
        self.assertEqual(new.status_code, 200)
        self.assertEqual(old.status_code, 400)

    # ---------- Once a week ----------

    def test_only_once_a_week(self, webpush):
        self.rename('annabel')
        self.assertIsNotNone(self.client.get('/api/me/').data['next_username_change'])
        response = self.rename('annie')
        self.assertEqual(response.status_code, 400)
        self.assertIn('once a week', response.data['username'][0])
        self.a_week_passes()
        self.assertIsNone(self.client.get('/api/me/').data['next_username_change'])
        self.assertEqual(self.rename('annie').status_code, 200)

    def test_a_capitals_only_change_counts_too(self, webpush):
        self.assertEqual(self.rename('Anna').status_code, 200)
        self.assertEqual(self.rename('annabel').status_code, 400)

    # ---------- Who is told ----------

    def test_friends_and_pending_requests_are_told(self, webpush):
        cleo = User.objects.create_user('cleo', password='pass12345')
        dan = User.objects.create_user('dan', password='pass12345')
        eve = User.objects.create_user('eve', password='pass12345')
        Friendship.objects.create(from_user=self.anna, to_user=self.ben, accepted=True)  # friend
        Friendship.objects.create(from_user=self.anna, to_user=cleo)  # I asked cleo
        Friendship.objects.create(from_user=dan, to_user=self.anna)  # dan asked me
        PushSubscription.objects.create(user=self.ben, endpoint='https://web.push.apple.com/ben', p256dh='k', auth='a')
        self.rename('annabel')
        for person in [self.ben, cleo, dan]:
            self.assertEqual(self.told(person), ['anna is now called annabel'])
        self.assertEqual(self.told(eve), [])  # a stranger
        self.assertEqual(self.told(self.anna), [])  # not me
        self.assertEqual(webpush.call_count, 1)  # pushed to ben's phone
        self.assertIn('anna is now called annabel', webpush.call_args.kwargs['data'])

    def test_capitals_only_tells_nobody(self, webpush):
        Friendship.objects.create(from_user=self.anna, to_user=self.ben, accepted=True)
        self.rename('Anna')
        self.assertEqual(self.told(self.ben), [])

    def test_the_message_keeps_both_names(self, webpush):
        Friendship.objects.create(from_user=self.anna, to_user=self.ben, accepted=True)
        self.rename('annabel')
        self.a_week_passes()
        self.rename('annie')
        self.client.force_authenticate(user=self.ben)
        messages = [n['message'] for n in self.client.get('/api/notifications/').data['notifications']]
        self.assertEqual(messages, ['annabel is now called annie', 'anna is now called annabel'])
