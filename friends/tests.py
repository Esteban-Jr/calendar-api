from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from events.models import Event
from .models import Friendship


class FriendTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.cleo = User.objects.create_user('cleo', password='pass12345')

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def make_friends(self, a, b):
        return Friendship.objects.create(from_user=a, to_user=b, accepted=True)

    def event_of(self, owner):
        return Event.objects.create(
            title='Dinner', start='2026-11-20T19:00:00Z', end='2026-11-20T21:00:00Z', owner=owner,
        )

    def test_friends_needs_a_token(self):
        self.assertEqual(self.client.get('/api/friends/').status_code, 401)

    def test_send_and_accept_a_request(self):
        self.as_user(self.anna)
        response = self.client.post('/api/friends/', {'username': 'ben'}, format='json')
        self.assertEqual(response.status_code, 201)
        request_id = response.data['id']
        self.assertEqual(self.client.get('/api/friends/').data['outgoing'], [{'id': request_id, 'username': 'ben'}])

        self.as_user(self.ben)
        self.assertEqual(self.client.get('/api/friends/').data['incoming'], [{'id': request_id, 'username': 'anna'}])
        self.assertEqual(self.client.post(f'/api/friends/{request_id}/accept/').status_code, 200)
        self.assertEqual(self.client.get('/api/friends/').data['friends'], [{'id': request_id, 'username': 'anna'}])

    def test_only_the_person_asked_can_accept(self):
        request = Friendship.objects.create(from_user=self.anna, to_user=self.ben)
        self.as_user(self.anna)
        self.assertEqual(self.client.post(f'/api/friends/{request.id}/accept/').status_code, 404)
        self.as_user(self.cleo)
        self.assertEqual(self.client.post(f'/api/friends/{request.id}/accept/').status_code, 404)

    def test_asking_someone_who_already_asked_you_accepts(self):
        Friendship.objects.create(from_user=self.ben, to_user=self.anna)
        self.as_user(self.anna)
        response = self.client.post('/api/friends/', {'username': 'ben'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Friendship.objects.get().accepted)

    def test_bad_requests_give_400(self):
        self.as_user(self.anna)
        for username in ['nobody', 'anna']:
            response = self.client.post('/api/friends/', {'username': username}, format='json')
            self.assertEqual(response.status_code, 400, username)
        self.client.post('/api/friends/', {'username': 'ben'}, format='json')
        self.assertEqual(self.client.post('/api/friends/', {'username': 'ben'}, format='json').status_code, 400)

    def test_username_is_not_case_sensitive(self):
        self.as_user(self.anna)
        self.assertEqual(self.client.post('/api/friends/', {'username': ' Ben '}, format='json').status_code, 201)

    def test_decline_or_cancel_a_request(self):
        request = Friendship.objects.create(from_user=self.anna, to_user=self.ben)
        self.as_user(self.ben)
        self.assertEqual(self.client.delete(f'/api/friends/{request.id}/').status_code, 204)
        self.assertFalse(Friendship.objects.exists())

    def test_strangers_cannot_remove_a_friendship(self):
        friendship = self.make_friends(self.anna, self.ben)
        self.as_user(self.cleo)
        self.assertEqual(self.client.delete(f'/api/friends/{friendship.id}/').status_code, 404)

    def test_can_only_share_with_friends(self):
        self.make_friends(self.anna, self.ben)
        event = self.event_of(self.anna)
        self.as_user(self.anna)
        ok = self.client.patch(f'/api/events/{event.id}/', {'shared_with': ['ben']}, format='json')
        self.assertEqual(ok.status_code, 200)
        not_ok = self.client.patch(f'/api/events/{event.id}/', {'shared_with': ['ben', 'cleo']}, format='json')
        self.assertEqual(not_ok.status_code, 400)
        self.assertIn('cleo', str(not_ok.data))

    def test_a_pending_request_is_not_enough_to_share(self):
        Friendship.objects.create(from_user=self.anna, to_user=self.ben)
        self.as_user(self.anna)
        response = self.client.post('/api/events/', {
            'title': 'Lunch', 'start': '2026-11-20T12:00:00Z', 'end': '2026-11-20T13:00:00Z', 'shared_with': ['ben'],
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_unfriending_stops_sharing_both_ways(self):
        friendship = self.make_friends(self.anna, self.ben)
        annas, bens = self.event_of(self.anna), self.event_of(self.ben)
        annas.shared_with.add(self.ben)
        bens.shared_with.add(self.anna)
        other = self.event_of(self.anna)
        other.shared_with.add(self.cleo)  # someone else's share is left alone

        self.as_user(self.ben)
        self.assertEqual(self.client.delete(f'/api/friends/{friendship.id}/').status_code, 204)
        self.assertFalse(annas.shared_with.exists())
        self.assertFalse(bens.shared_with.exists())
        self.assertEqual(list(other.shared_with.all()), [self.cleo])
