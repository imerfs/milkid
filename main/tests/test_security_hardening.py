"""Hardening round: staff need a village, /media/ files are readable only by their parties, logout cannot be triggered from another site, CSP basics."""
from unittest import mock

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from main import media_access
from main.models import RequestDocument, ServiceRequest
from main.request_scope import in_scope
from django.contrib.auth.models import User

from main.tests.helpers import client_for, make_user


def fresh(user):
    """make_user writes the role straight to the database; reload so the cached profile is not stale."""
    return User.objects.get(pk=user.pk)


class Media(TestCase):
    def setUp(self):
        self.owner = fresh(make_user('citizen'))
        self.other = fresh(make_user('citizen'))
        self.admin = fresh(make_user('admin'))
        sr = ServiceRequest.objects.create(user=self.owner, title='t', description='d') if hasattr(ServiceRequest, 'description') else ServiceRequest.objects.create(user=self.owner, title='t')
        self.doc = RequestDocument(request=sr, document_name='x')
        self.doc.document.save('a.pdf', ContentFile(b'%PDF-1.4'))
        self.rel = self.doc.document.name

    def test_only_the_owner_and_admin_read_request_documents(self):
        self.assertTrue(media_access.can_read(self.owner, self.rel))
        self.assertTrue(media_access.can_read(self.admin, self.rel))
        self.assertFalse(media_access.can_read(self.other, self.rel))

    def test_unknown_protected_paths_are_refused_and_public_folders_stay_open(self):
        self.assertFalse(media_access.can_read(self.owner, 'request_documents/none.pdf'))
        self.assertTrue(media_access.can_read(self.owner, 'news/pic.jpg'))

    def test_relative_path_refuses_escapes(self):
        self.assertEqual(media_access.relative_path('/media/letters/a.pdf?x=1'), 'letters/a.pdf')
        self.assertIsNone(media_access.relative_path('/media/../etc/passwd'))
        self.assertIsNone(media_access.relative_path('/static/a.js'))

    def test_auth_endpoint_uses_the_original_address(self):
        url = reverse('main:media_auth')
        self.assertEqual(Client().get(url).status_code, 401)
        c = client_for(self.other)
        self.assertEqual(c.get(url, HTTP_X_ORIGINAL_URI='/media/' + self.rel).status_code, 403)
        self.assertEqual(client_for(self.owner).get(url, HTTP_X_ORIGINAL_URI='/media/' + self.rel).status_code, 204)
        self.assertEqual(c.get(url).status_code, 204)             # nginx config from before the check: signed-in rule only


class Logout(TestCase):
    def test_a_cross_site_get_only_asks_for_confirmation(self):
        c = client_for(make_user('citizen'))
        page = c.get('/logout/', HTTP_SEC_FETCH_SITE='cross-site')
        self.assertContains(page, 'خروج')
        self.assertIn('_auth_user_id', c.session)                  # still signed in
        c.post('/logout/')
        self.assertNotIn('_auth_user_id', c.session)

    def test_a_same_site_link_still_signs_out(self):
        c = client_for(make_user('citizen'))
        c.get('/logout/', HTTP_SEC_FETCH_SITE='same-origin')
        self.assertEqual(c.get('/dashboard/').status_code, 302)


class Staff(TestCase):
    def test_staff_without_a_village_see_no_request(self):
        staff = fresh(make_user('dehyari', city_village='', city_village_name=''))
        sr = ServiceRequest.objects.create(user=make_user('citizen'), title='t')
        self.assertFalse(in_scope(staff, sr))
        self.assertTrue(in_scope(fresh(make_user('admin')), sr))


@override_settings(DEBUG=False)
class Headers(TestCase):
    def test_csp_basics(self):
        csp = Client().get('/')['Content-Security-Policy']
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertIn("object-src 'none'", csp)
