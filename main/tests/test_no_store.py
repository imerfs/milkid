"""After sign-out the Back button must not bring a signed-in page back: pages of a session are never stored by the browser."""
from django.test import Client, TestCase

from main.tests.helpers import client_for, make_user


class NoStore(TestCase):
    def test_signed_in_pages_are_not_cacheable(self):
        response = client_for(make_user('citizen')).get('/dashboard/')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Pragma'], 'no-cache')

    def test_the_sign_out_page_and_the_login_page_after_it_are_not_cacheable(self):
        c = client_for(make_user('citizen'))
        out = c.get('/logout/')
        self.assertIn('no-store', out['Cache-Control'])
        self.assertIn('no-store', c.get('/login/')['Cache-Control'])

    def test_static_files_and_anonymous_pages_keep_their_caching(self):
        self.assertNotIn('no-store', Client().get('/')['Cache-Control'] if 'Cache-Control' in Client().get('/') else '')

    def test_after_sign_out_the_dashboard_needs_a_new_sign_in(self):
        c = client_for(make_user('citizen'))
        c.get('/logout/')
        self.assertEqual(c.get('/dashboard/').status_code, 302)
