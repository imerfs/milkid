"""Municipality registration: server errors must all show at once, on a single page."""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class RegisterMunicipalityErrorsTest(TestCase):
    def setUp(self):
        cache.clear()  # /register is throttled per IP; other tests share the cache

    def test_invalid_post_lists_every_error(self):
        resp = self.client.post(reverse('main:register_municipality'), {})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Errors of fields from every section are listed together
        for label in ('استان', 'رمز عبور مدیر سیستم', 'نام کاربری مدیر سیستم'):
            self.assertIn(f'<strong>{label}:</strong>', html)
