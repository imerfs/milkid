import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.office.visits import panel_url
from main.tests.helpers import client_for, make_municipality, make_user

VILLAGE = 'روستای الف'


class Navigation(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.accountant = make_user('accountant', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)

    def get(self, user, name):
        return client_for(user).get(reverse(f'main:{name}'), follow=True).content.decode()

    def test_navbar_links_to_letters_and_appointments(self):
        page = self.get(self.citizen, 'my_requests')
        self.assertIn(reverse('main:letters_inbox'), page)
        self.assertIn(panel_url(User.objects.get(pk=self.citizen.pk)), page)      # the section inside the citizen's own panel
        self.assertNotIn(reverse('main:role_grants'), page)       # only for the dehyari/admin

    def test_only_the_dehyari_sees_the_roles_link(self):
        self.assertIn(reverse('main:role_grants'), self.get(self.dehyari, 'my_requests'))
        self.assertNotIn(reverse('main:role_grants'), self.get(self.accountant, 'my_requests'))

    def test_unread_letter_count_shows_in_the_navbar(self):
        client_for(self.dehyari).post(reverse('main:letter_compose'), {
            'to': [self.accountant.id], 'subject': 's', 'body': 'b', 'action': 'send', 'token': str(uuid.uuid4())})
        page = self.get(self.accountant, 'my_requests')
        self.assertIn('badge bg-danger">1<', page)

    def test_dashboards_carry_the_office_dock(self):
        for who, name in ((self.accountant, 'accountant_dashboard'), (self.dehyari, 'dehyari_dashboard')):
            page = self.get(who, name)
            self.assertIn('aria-label="میان‌بر پیام‌ها و وقت‌ها"', page, name)
            self.assertIn(reverse('main:messenger'), page, name)          # the messenger opens as a drawer over the panel
            self.assertIn('id="mg-drawer"', page, name)
        self.assertIn(reverse('main:mayor_panel', args=['employees']), self.get(self.dehyari, 'dehyari_dashboard'))

    def test_mayor_staff_tab_opens_inside_the_panel(self):
        page = self.get(self.dehyari, 'dehyari_dashboard')
        self.assertIn('data-tab-link', page)
        r = client_for(self.dehyari).get(reverse('main:mayor_staff_list'))
        self.assertRedirects(r, reverse('main:role_grants'), fetch_redirect_response=False)
