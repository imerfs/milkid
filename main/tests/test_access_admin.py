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
