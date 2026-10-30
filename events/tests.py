from rest_framework.test import APITestCase
from django.contrib.auth.models import User
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