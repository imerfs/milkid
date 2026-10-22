"""The support address on the public pages comes from settings (a .env change), not from the templates."""
from django.test import TestCase, override_settings
from django.urls import reverse


class SupportEmailTests(TestCase):
    @override_settings(SUPPORT_EMAIL='help@example.test')
    def test_contact_page_shows_the_configured_address(self):
        page = self.client.get(reverse('main:contact'))
        self.assertContains(page, 'help@example.test')
        self.assertNotContains(page, 'amirl.ir')

    @override_settings(SUPPORT_EMAIL='help@example.test')
    def test_home_page_shows_it_too(self):
        self.assertContains(self.client.get(reverse('main:home')), 'help@example.test')

    def test_default_follows_the_sender_address_and_is_on_the_new_domain(self):
        from django.conf import settings
        self.assertEqual(settings.SUPPORT_EMAIL, settings.DEFAULT_FROM_EMAIL)
        self.assertTrue(settings.DEFAULT_FROM_EMAIL.endswith('@milkid.ir'))
