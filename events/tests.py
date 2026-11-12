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
        self.assertEqual(response.data, {'id': user.id, 'username': 'anna'})

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
