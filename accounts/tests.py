import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import PendingSignup, ResetCode

STRONG = 'Sunflower-Pancake-42'


def last_code():
    """The 6-digit code in the most recent email."""
    return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)


class AccountTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # the rate limits live in the cache

    def register(self, username='ana', email='ana@example.com', password=STRONG):
        return self.client.post('/api/auth/register/', {
            'username': username, 'email': email, 'password': password,
        }, format='json')

    def make_user(self, username='ana', email='ana@example.com', password=STRONG):
        return User.objects.create_user(username, email, password)

    def age(self, entry, **delta):
        entry.created_at = timezone.now() - timedelta(**delta)
        entry.save(update_fields=['created_at'])


class RegisterTests(AccountTestCase):
    def test_register_sends_a_code_and_creates_no_user_yet(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ana@example.com'])
        self.assertFalse(User.objects.filter(username='ana').exists())
        self.assertTrue(PendingSignup.objects.filter(email='ana@example.com').exists())

    def test_the_plain_password_and_code_are_never_stored(self):
        self.register()
        pending = PendingSignup.objects.get()
        self.assertNotIn(STRONG, pending.password_hash)
        self.assertNotIn(last_code(), pending.code_hash)

    def test_correct_code_creates_the_user_and_returns_a_token(self):
        self.register()
        response = self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': last_code()}, format='json')
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='ana')
        self.assertEqual(response.data['token'], Token.objects.get(user=user).key)
        self.assertTrue(user.check_password(STRONG))
        self.assertFalse(PendingSignup.objects.exists())

    def test_wrong_code_is_refused_and_creates_nobody(self):
        self.register()
        wrong = '000000' if last_code() != '000000' else '111111'
        response = self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': wrong}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='ana').exists())

    def test_five_wrong_codes_kill_the_real_one(self):
        self.register()
        real = last_code()
        wrong = '000000' if real != '000000' else '111111'
        for _ in range(5):
            self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': wrong}, format='json')
        response = self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': real}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username='ana').exists())

    def test_expired_code_is_refused(self):
        self.register()
        self.age(PendingSignup.objects.get(), minutes=16)
        response = self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': last_code()}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_taken_username_and_email_are_refused(self):
        self.make_user('bea', 'bea@example.com')
        self.assertEqual(self.register(username='BEA', email='new@example.com').status_code, 400)
        self.assertEqual(self.register(username='new', email='BEA@example.com').status_code, 400)

    def test_weak_passwords_are_refused(self):
        self.assertEqual(self.register(password='12345678').status_code, 400)
        self.assertEqual(self.register(password='short').status_code, 400)

    def test_asking_again_straight_away_is_refused_with_429(self):
        self.register()
        self.assertEqual(self.register().status_code, 429)

    def test_resend_gives_a_fresh_code_after_the_wait(self):
        self.register()
        first = last_code()
        self.age(PendingSignup.objects.get(), seconds=61)
        response = self.client.post('/api/auth/resend/', {'email': 'ana@example.com'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        response = self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': last_code()}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(first), 6)

    def test_resend_for_an_unknown_email_looks_the_same(self):
        response = self.client.post('/api/auth/resend/', {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_too_many_registrations_from_one_address_are_rate_limited(self):
        for i in range(15):
            self.register(username=f'u{i}', email=f'u{i}@example.com')
        self.assertEqual(self.register(username='u99', email='u99@example.com').status_code, 429)

    @override_settings(ALLOW_REGISTRATION=False)
    def test_registration_can_be_closed(self):
        self.assertEqual(self.register().status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_failure_leaves_nothing_behind(self):
        from unittest import mock
        with mock.patch('accounts.views.send_code_email', side_effect=OSError('smtp down')):
            response = self.register()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(PendingSignup.objects.exists())

    def test_new_user_can_log_in_with_the_password(self):
        self.register()
        self.client.post('/api/auth/verify/', {'email': 'ana@example.com', 'code': last_code()}, format='json')
        response = self.client.post('/api-auth/', {'username': 'ana', 'password': STRONG}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)


class ForgotPasswordTests(AccountTestCase):
    def test_forgot_then_reset_changes_the_password(self):
        user = self.make_user()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post('/api/auth/reset/', {
            'email': 'ana@example.com', 'code': last_code(), 'password': 'Brand-New-Pass-77',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Brand-New-Pass-77'))
        self.assertFalse(ResetCode.objects.exists())

    def test_unknown_email_gets_the_same_answer_and_no_email(self):
        known = self.make_user()
        a = self.client.post('/api/auth/forgot/', {'email': known.email}, format='json')
        b = self.client.post('/api/auth/forgot/', {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(len(mail.outbox), 1)  # only the real account was emailed

    def test_wrong_code_does_not_change_the_password(self):
        user = self.make_user()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        real = last_code()
        wrong = '000000' if real != '000000' else '111111'
        response = self.client.post('/api/auth/reset/', {
            'email': 'ana@example.com', 'code': wrong, 'password': 'Brand-New-Pass-77',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password(STRONG))

    def test_a_code_works_only_once(self):
        self.make_user()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        code = last_code()
        body = {'email': 'ana@example.com', 'code': code, 'password': 'Brand-New-Pass-77'}
        self.assertEqual(self.client.post('/api/auth/reset/', body, format='json').status_code, 200)
        body['password'] = 'Another-Pass-88'
        self.assertEqual(self.client.post('/api/auth/reset/', body, format='json').status_code, 400)

    def test_weak_new_password_is_refused_and_the_code_survives(self):
        self.make_user()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        code = last_code()
        response = self.client.post('/api/auth/reset/', {'email': 'ana@example.com', 'code': code, 'password': '12345678'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)
        response = self.client.post('/api/auth/reset/', {'email': 'ana@example.com', 'code': code, 'password': 'Brand-New-Pass-77'}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_reset_signs_out_other_devices(self):
        user = self.make_user()
        token = Token.objects.create(user=user)
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        self.client.post('/api/auth/reset/', {'email': 'ana@example.com', 'code': last_code(), 'password': 'Brand-New-Pass-77'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/me/').status_code, 401)

    def test_asking_twice_quickly_sends_only_one_email(self):
        self.make_user()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_accounts_are_not_emailed(self):
        user = self.make_user()
        user.is_active = False
        user.save()
        self.client.post('/api/auth/forgot/', {'email': 'ana@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 0)


class LoginTests(AccountTestCase):
    def test_login_is_rate_limited(self):
        self.make_user()
        for _ in range(30):
            self.client.post('/api-auth/', {'username': 'ana', 'password': 'wrong'}, format='json')
        response = self.client.post('/api-auth/', {'username': 'ana', 'password': STRONG}, format='json')
        self.assertEqual(response.status_code, 429)
