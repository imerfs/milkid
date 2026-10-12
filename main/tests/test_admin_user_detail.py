"""Admin-only read-only detail page for a single user."""
from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user


class AdminUserDetail(TestCase):
    def url(self, user):
        return reverse('main:admin_user_detail', args=[user.id])

    def test_admin_sees_profile_data_without_secrets(self):
        target = make_user('citizen', national_id='0012345678', mobile_number='09121234567')
        response = client_for(make_user('admin')).get(self.url(target))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target.username)
        self.assertContains(response, '0012345678')
        self.assertNotContains(response, target.password)

    def test_non_admins_and_anonymous_are_refused(self):
        target = make_user('citizen')
        for role in ('citizen', 'owner', 'dehyari', 'engineer', 'inspector', 'accountant', 'council'):
            with self.subTest(role=role):
                self.assertIn(client_for(make_user(role)).get(self.url(target)).status_code, (302, 403, 404))
        response = client_for().get(self.url(target))
        self.assertIn(response.status_code, (302, 403))

    def test_unknown_user_is_404_for_admin(self):
        response = client_for(make_user('admin')).get(reverse('main:admin_user_detail', args=[999999]))
        self.assertEqual(response.status_code, 404)
