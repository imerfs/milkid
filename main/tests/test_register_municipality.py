"""Municipality registration: server errors must all show at once, on a single page."""
from django.test import TestCase
from django.urls import reverse


class RegisterMunicipalityErrorsTest(TestCase):
    def test_invalid_post_shows_all_steps_and_every_error(self):
        resp = self.client.post(reverse('main:register_municipality'), {})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Wizard collapses into one page so the user does not click "next" again
        self.assertIn('class="show-all"', html)
        # Errors of fields from different wizard steps are listed together
        for label in ('استان', 'رمز عبور مدیر سیستم', 'نام کاربری مدیر سیستم'):
            self.assertIn(f'<strong>{label}:</strong>', html)

    def test_get_keeps_wizard(self):
        resp = self.client.get(reverse('main:register_municipality'))
        self.assertNotIn('class="show-all"', resp.content.decode())
