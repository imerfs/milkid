from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user

PAGES = ['home', 'about', 'contact', 'services_catalog', 'property_listings', 'my_requests', 'notifications',
         'letters_inbox', 'appointments', 'appointment_providers', 'messaging_dashboard', 'announcement_list',
         'dashboard']
ROLES = ['admin', 'dehyari', 'engineer', 'inspector', 'accountant', 'council', 'owner', 'citizen']


class EveryRoleCanOpenTheCommonPages(TestCase):
    """The navbar queries the database on every page; a missing table/column must never take pages down."""

    def test_no_server_errors(self):
        for role in ROLES:
            client = client_for(make_user(role))
            for name in PAGES:
                response = client.get(reverse(f'main:{name}'), follow=True)
                self.assertLess(response.status_code, 500, f'{name} as {role}')
