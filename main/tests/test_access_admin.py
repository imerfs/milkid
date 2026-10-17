"""The admin panel's pages and JSON endpoints must refuse everyone except admins."""
from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user

PAGES = ['admin_dashboard', 'manage_users', 'manage_requests', 'manage_municipalities', 'manage_property_ads']
API_NO_ARGS = ['api_admin_users_list', 'api_admin_municipalities_list', 'api_admin_services_list',
               'api_admin_service_create', 'api_admin_reports_chart_data', 'api_admin_system_settings',
               'api_admin_update_system_settings', 'api_admin_users_monitoring_stats']
API_WITH_ID = ['api_admin_user_change_role', 'api_admin_user_toggle_active', 'api_admin_municipality_action',
               'api_admin_service_update', 'api_admin_service_delete', 'api_admin_service_toggle_active']


def urls():
    for name in PAGES:
        yield name, reverse(f'main:{name}'), False
    for name in API_NO_ARGS:
        yield name, reverse(f'main:{name}'), True
    for name in API_WITH_ID:
        yield name, reverse(f'main:{name}', args=[999999]), True


class AdminSurfaceIsAdminOnly(TestCase):
    def assert_refused(self, client, who):
        for name, url, is_api in urls():
            for method in (client.get, client.post):
                response = method(url)
                with self.subTest(who=who, endpoint=name, method=method.__name__):
                    self.assertIn(response.status_code, (302, 401, 403), f'{name} answered {response.status_code}')
                    if who == 'anonymous' and response.status_code == 302:
                        self.assertIn('/login/', response['Location'])

    def test_anonymous_is_refused_everywhere(self):
        self.assert_refused(client_for(), 'anonymous')

    def test_every_non_admin_role_is_refused_everywhere(self):
        for role in ('citizen', 'owner', 'dehyari', 'engineer', 'inspector', 'accountant', 'council'):
            self.assert_refused(client_for(make_user(role)), role)

    def test_admin_still_reaches_the_pages_and_lists(self):
        admin = client_for(make_user('admin'))
        for name in ('manage_users', 'manage_requests', 'manage_municipalities', 'manage_property_ads',
                     'api_admin_users_list', 'api_admin_municipalities_list', 'api_admin_services_list',
                     'api_admin_system_settings'):
            with self.subTest(endpoint=name):
                self.assertEqual(admin.get(reverse(f'main:{name}')).status_code, 200)

    def test_a_citizen_cannot_make_themselves_admin(self):
        citizen = make_user('citizen')
        client_for(citizen).post(reverse('main:api_admin_user_change_role', args=[citizen.profile.id]),
                                 data='{"role": "admin"}', content_type='application/json')
        citizen.profile.refresh_from_db()
        self.assertEqual(citizen.profile.role, 'citizen')


class AdminApiGuards(TestCase):
    """The admin JSON endpoints use the access policy: Django's is_staff flag alone is not enough."""

    URLS = ('api_admin_approve_property_ad', 'api_admin_toggle_user_access')

    def call(self, user, name):
        from django.urls import reverse
        return client_for(user).post(reverse(f'main:{name}', args=[999999]))

    def test_a_staff_flag_without_the_admin_role_is_refused(self):
        user = make_user('citizen')
        user.is_staff = True
        user.save()
        for name in self.URLS:
            with self.subTest(name=name):
                self.assertEqual(self.call(user, name).status_code, 403)

    def test_admins_and_superusers_get_past_the_guard(self):
        from django.contrib.auth.models import User
        superuser = User.objects.create_superuser('root-guard', password='pw-test-12345')
        for who in (make_user('admin'), superuser):
            for name in self.URLS:
                with self.subTest(name=name):
                    self.assertEqual(self.call(who, name).status_code, 404)      # allowed in; the object does not exist
