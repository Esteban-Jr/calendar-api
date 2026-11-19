"""API answers must never be reused from a cache (SO/BE14): otherwise a phone
can show an old notifications list, and the bell keeps Accept / Decline."""
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase


class NoStoreTests(APITestCase):
    def setUp(self):
        cache.clear()  # the login is rate-limited per IP
        self.anna = User.objects.create_user('anna', password='pass12345')

    def assertNoStore(self, response):
        self.assertIn('no-store', response.get('Cache-Control', ''))

    def test_the_bell_is_never_cached(self):
        self.client.force_authenticate(user=self.anna)
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertNoStore(response)

    def test_the_event_list_is_never_cached(self):
        self.client.force_authenticate(user=self.anna)
        self.assertNoStore(self.client.get('/api/events/'))

    def test_errors_are_never_cached_either(self):
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 401)
        self.assertNoStore(response)

    def test_the_login_token_is_never_cached(self):
        response = self.client.post('/api-auth/', {'username': 'anna', 'password': 'pass12345'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNoStore(response)

    def test_pages_outside_the_api_are_left_alone(self):
        response = self.client.get('/')
        self.assertNotIn('no-store', response.get('Cache-Control', ''))
