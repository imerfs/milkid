from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings


class AnonymousAccessTests(TestCase):
    def test_payment_export_requires_login(self):
        r = self.client.get('/api/payments/export-excel/')
        self.assertEqual(r.status_code, 401)

    def test_payment_export_denied_for_ordinary_user(self):
        User.objects.create_user('citizen', password='x-pass-1234')
        self.client.login(username='citizen', password='x-pass-1234')
        r = self.client.get('/api/payments/export-excel/')
        self.assertEqual(r.status_code, 403)

    def test_private_views_redirect_anonymous_instead_of_crashing(self):
        for path in ('/payments/', '/api/notifications/', '/dashboard/'):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn('/login/', r['Location'])

    def test_debug_pages_are_gone(self):
        self.assertEqual(self.client.get('/test-geographic/').status_code, 404)
        self.assertEqual(self.client.get('/test/jalali-dates/').status_code, 404)


class MediaAuthTests(TestCase):
    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get('/_media-auth/').status_code, 401)

    def test_signed_in_user_is_accepted(self):
        User.objects.create_user('u', password='x-pass-1234')
        self.client.login(username='u', password='x-pass-1234')
        self.assertEqual(self.client.get('/_media-auth/').status_code, 204)


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_brute_force_is_throttled(self):
        codes = [self.client.post('/login/', {'username': 'a', 'password': 'b'},
                                  HTTP_X_REAL_IP='203.0.113.9').status_code for _ in range(12)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:10])

    def test_spoofed_forwarded_for_does_not_bypass_limit(self):
        last = None
        for i in range(12):
            last = self.client.post('/login/', {'username': 'a', 'password': 'b'},
                                    HTTP_X_REAL_IP='203.0.113.10',
                                    HTTP_X_FORWARDED_FOR=f'198.51.100.{i}').status_code
        self.assertEqual(last, 429)
