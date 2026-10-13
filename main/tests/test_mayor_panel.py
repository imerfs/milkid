"""The dehyari panel keeps employees, requests, announcements and profile on one page."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Announcement, ServiceRequest, UserProfile
from main.tests.helpers import client_for, make_municipality, make_user

def mk(owner, title):
    return ServiceRequest.objects.create(user=owner, request_type='other', title=title, description='d')


TABS = ('employees', 'requests', 'announcements', 'profile')


class Panel(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari', city_village='روستای الف')
        make_municipality(self.dehyari, 'روستای الف')
        self.staff = make_user('accountant', city_village='روستای الف')
        self.other_staff = make_user('accountant', city_village='روستای ب')

    def tab(self, who, name, **extra):
        return client_for(who).get(reverse('main:mayor_panel', args=[name]), **extra)


class Access(Panel):
    def test_only_the_dehyari_may_open_a_tab(self):
        for name in TABS:
            for who in (None, make_user('citizen'), self.staff):
                r = self.tab(who, name)
                self.assertEqual(r.status_code, 302, (name, who))
                self.assertNotIn(b'mp-pane', r.content)
            self.assertEqual(self.tab(self.dehyari, name).status_code, 200, name)

    def test_unknown_tab_is_404(self):
        self.assertEqual(self.tab(self.dehyari, 'nope').status_code, 404)

    def test_dashboard_has_no_links_leaving_the_page_for_the_four_tabs(self):
        page = client_for(self.dehyari).get(reverse('main:dehyari_dashboard')).content.decode()
        for url in (reverse('main:mayor_requests_list'), reverse('main:announcement_list'),
                    reverse('main:user_profile')):
            self.assertNotIn(f'href="{url}"', page)
        for name in TABS:
            self.assertIn(reverse('main:mayor_panel', args=[name]), page)

    def test_old_urls_deep_link_to_the_tab(self):
        c = client_for(self.dehyari)
        r = c.get(reverse('main:mayor_requests_list'))
        self.assertRedirects(r, reverse('main:dehyari_dashboard') + '?tab=requests', fetch_redirect_response=False)
        self.assertRedirects(c.get(reverse('main:role_grants')),
                             reverse('main:dehyari_dashboard') + '?tab=employees', fetch_redirect_response=False)

    def test_panel_header_keeps_the_old_pages_for_fetches(self):
        r = client_for(self.dehyari).get(reverse('main:role_grants'), HTTP_X_PANEL='1')
        self.assertEqual(r.status_code, 200)


class Employees(Panel):
    def test_lists_only_this_villages_staff(self):
        html = self.tab(self.dehyari, 'employees').content.decode()
        self.assertIn(self.staff.username, html)
        self.assertNotIn(self.other_staff.username, html)

    def test_error_from_a_role_action_is_json_for_the_panel(self):
        r = client_for(self.dehyari).post(reverse('main:role_grant'), {'user_id': 999999, 'role': 'engineer'},
                                          HTTP_X_PANEL='1')
        self.assertGreaterEqual(r.status_code, 400)
        self.assertIn('error', r.json())


class Requests(Panel):
    def test_lists_only_this_villages_requests_and_filters(self):
        mine = mk(make_user('citizen', city_village='روستای الف'), 'درخواست من')
        theirs = mk(make_user('citizen', city_village='روستای ب'), 'درخواست بیگانه')
        html = self.tab(self.dehyari, 'requests').content.decode()
        self.assertIn(mine.title, html)
        self.assertNotIn(theirs.title, html)
        html = self.tab(self.dehyari, 'requests', QUERY_STRING='status=approved').content.decode()
        self.assertNotIn(mine.title, html)

    def test_empty_village_shows_empty_state_not_everything(self):
        lone = make_user('dehyari')   # no municipality yet
        mk(make_user('citizen'), 'نباید دیده شود')
        html = self.tab(lone, 'requests').content.decode()
        self.assertNotIn('نباید دیده شود', html)


class Announcements(Panel):
    def test_lists_own_announcements_only(self):
        Announcement.objects.create(title='اطلاعیه من', content='x', created_by=self.dehyari)
        Announcement.objects.create(title='اطلاعیه دیگری', content='x', created_by=make_user('dehyari'))
        html = self.tab(self.dehyari, 'announcements').content.decode()
        self.assertIn('اطلاعیه من', html)
        self.assertNotIn('اطلاعیه دیگری', html)


class Profile(Panel):
    def save(self, **data):
        base = {'first_name': 'علی', 'last_name': 'رضایی', 'email': 'a@b.ir', 'mobile_number': '09121234567'}
        base.update(data)
        return client_for(self.dehyari).post(reverse('main:mayor_panel', args=['profile']), base)

    def test_saves_name_email_and_mobile(self):
        r = self.save()
        self.assertEqual(r.status_code, 200)
        self.dehyari.refresh_from_db()
        self.assertEqual((self.dehyari.first_name, self.dehyari.email), ('علی', 'a@b.ir'))
        self.assertEqual(UserProfile.objects.get(user=self.dehyari).mobile_number, '09121234567')

    def test_rejects_bad_mobile_empty_name_and_long_text(self):
        for bad in ({'mobile_number': '123'}, {'first_name': ''}, {'last_name': 'ا' * 200}, {'email': 'nope'}):
            r = self.save(**bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertTrue(r.json()['errors'])
        self.dehyari.refresh_from_db()
        self.assertEqual(self.dehyari.first_name, '')

    def test_password_change_in_place(self):
        url = reverse('main:mayor_panel', args=['profile'])
        c = client_for(self.dehyari)
        self.dehyari.set_password('Old-pass-12345')
        self.dehyari.save()
        c.force_login(self.dehyari)
        r = c.post(url, {'action': 'password', 'old_password': 'wrong', 'new_password': 'New-pass-98765',
                         'new_password2': 'New-pass-98765'})
        self.assertEqual(r.status_code, 400)
        r = c.post(url, {'action': 'password', 'old_password': 'Old-pass-12345', 'new_password': 'New-pass-98765',
                         'new_password2': 'New-pass-98765'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(pk=self.dehyari.pk).check_password('New-pass-98765'))
        self.assertEqual(c.get(url).status_code, 200)   # session survived

    def test_other_users_cannot_post(self):
        r = client_for(self.staff).post(reverse('main:mayor_panel', args=['profile']), {'first_name': 'x'})
        self.assertEqual(r.status_code, 302)
