"""The administrative expert (کارشناس اداری): giving the role, the desk page, the reminder."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Notification, RoleGrant, UserProfile
from main.office import desk, letters
from main.tests.helpers import client_for, make_municipality, make_request, make_user

VILLAGE, OTHER = 'روستای الف', 'روستای ب'


class Village(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.clerk = make_user('clerk', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)
        # make_user updates the profile row behind the cached object; reload so direct calls see the real role
        self.dehyari, self.clerk = (User.objects.get(pk=u.pk) for u in (self.dehyari, self.clerk))


class GivingTheRole(Village):
    def test_dehyari_grants_and_revokes_the_role(self):
        client = client_for(self.dehyari)
        client.post(reverse('main:role_grant'), {'user_id': self.citizen.id, 'role': 'clerk'})
        self.assertEqual(UserProfile.objects.get(user=self.citizen).role, 'clerk')
        self.assertTrue(RoleGrant.objects.filter(user=self.citizen, role='clerk', revoked_at__isnull=True).exists())
        client.post(reverse('main:role_revoke', args=[self.citizen.id]))
        self.assertEqual(UserProfile.objects.get(user=self.citizen).role, 'citizen')

    def test_dehyari_creates_a_clerk_account(self):
        response = client_for(self.dehyari).post(reverse('main:role_create_account'), {
            'first_name': 'سارا', 'last_name': 'احمدی', 'username': 'sara.clerk', 'national_id': '0012345678',
            'mobile_number': '09121234567', 'role': 'clerk'})
        self.assertLess(response.status_code, 400)
        self.assertEqual(UserProfile.objects.get(user__username='sara.clerk').role, 'clerk')

    def test_clerk_lands_on_the_desk_after_login(self):
        response = client_for(self.clerk).get(reverse('main:dashboard'))
        self.assertRedirects(response, reverse('main:clerk_dashboard'), fetch_redirect_response=False)


class WhoMayOpenTheDesk(Village):
    def test_clerk_and_dehyari_open_it(self):
        for user in (self.clerk, self.dehyari):
            self.assertEqual(client_for(user).get(reverse('main:clerk_dashboard')).status_code, 200, user)

    def test_other_roles_are_turned_away(self):
        for role in ('citizen', 'owner', 'engineer', 'inspector', 'accountant', 'council'):
            response = client_for(make_user(role)).get(reverse('main:clerk_dashboard'))
            self.assertRedirects(response, reverse('main:dashboard'), fetch_redirect_response=False)

    def test_anonymous_goes_to_login(self):
        response = client_for().get(reverse('main:clerk_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('main:login'), response.url)

    def test_reminder_is_closed_to_other_roles(self):
        sr = make_request(self.citizen, status='requires_documents')
        for role in ('citizen', 'accountant'):
            client_for(make_user(role, city_village=VILLAGE)).post(reverse('main:clerk_remind', args=[sr.id]))
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())


class TheDeskPage(Village):
    def open(self, user=None, **params):
        return client_for(user or self.clerk).get(reverse('main:clerk_dashboard'), params)

    def test_empty_desk_renders(self):
        self.assertContains(self.open(), 'کار عقب‌افتاده‌ای ندارید')
        self.assertContains(self.open(tab='follow'), 'درخواستی منتظر مدارک نیست')

    def test_counts_unread_letters_and_lists_them(self):
        letters.compose(self.dehyari, to=[self.clerk.id], subject='گزارش ماهانه', body='متن')
        response = self.open()
        self.assertEqual(response.context['stats']['unread'], 1)
        self.assertContains(response, 'گزارش ماهانه')

    def test_follow_ups_are_limited_to_the_village(self):
        mine = make_request(self.citizen, status='requires_documents', title='نقشه ساختمان')
        foreign = make_request(make_user('citizen', city_village=OTHER), status='requires_documents', title='درخواست غریبه')
        make_request(self.citizen, status='pending', title='در جریان')
        response = self.open(tab='follow')
        self.assertContains(response, mine.title)
        self.assertNotContains(response, foreign.title)
        self.assertNotContains(response, 'در جریان')
        self.assertEqual(response.context['stats']['waiting_docs'], 1)

    def test_clerk_without_a_village_sees_no_requests(self):
        make_request(self.citizen, status='requires_documents')
        response = self.open(make_user('clerk'))
        self.assertEqual(response.context['stats']['waiting_docs'], 0)


class TheReminder(Village):
    def remind(self, sr, user=None):
        return client_for(user or self.clerk).post(reverse('main:clerk_remind', args=[sr.id]), follow=True)

    def test_citizen_is_notified_once_a_day(self):
        sr = make_request(self.citizen, status='requires_documents', title='نقشه ساختمان')
        self.remind(sr)
        self.assertEqual(Notification.objects.filter(user=self.citizen, title=desk.REMINDER_TITLE, related_request=sr).count(), 1)
        again = self.remind(sr)
        self.assertEqual(Notification.objects.filter(user=self.citizen, title=desk.REMINDER_TITLE).count(), 1)
        self.assertContains(again, 'یادآوری فرستاده شده است')

    def test_other_village_request_is_not_reachable(self):
        sr = make_request(make_user('citizen', city_village=OTHER), status='requires_documents')
        self.remind(sr)
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())

    def test_request_that_no_longer_waits_is_not_reminded(self):
        sr = make_request(self.citizen, status='approved')
        self.remind(sr)
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())

    def test_get_is_not_allowed(self):
        sr = make_request(self.citizen, status='requires_documents')
        response = client_for(self.clerk).get(reverse('main:clerk_remind', args=[sr.id]))
        self.assertEqual(response.status_code, 405)


class LettersReachTheClerk(Village):
    def test_clerk_can_write_to_and_receive_from_colleagues(self):
        sent = letters.compose(self.clerk, to=[self.dehyari.id], subject='ارسال از میز اداری', body='سلام')
        self.assertEqual(sent.status, 'sent')
        self.assertIn(self.clerk, [u for u in letters.allowed_recipients(self.dehyari)])


class Tabs(Village):
    def open(self, **params):
        return client_for(self.clerk).get(reverse('main:clerk_dashboard'), params)

    def test_every_tab_renders_and_unknown_tab_falls_back_to_today(self):
        for tab in ('today', 'messages', 'follow'):
            self.assertContains(self.open(tab=tab), f'cd-tabs', msg_prefix=tab)
        self.assertEqual(self.open(tab='nonsense').context['tab'], 'today')
        self.assertEqual(self.open(tab='visits').context['tab'], 'today')      # appointments are not the clerk's

    def test_messages_tab_holds_the_messenger_inline(self):
        page = self.open(tab='messages')
        self.assertContains(page, 'id="mg"')
        self.assertContains(page, 'messenger.js')

    def test_opening_a_thread_from_the_today_tab_links_into_the_messenger_tab(self):
        letters.compose(self.dehyari, to=[self.clerk.id], subject='نامه‌ی امروز', body='متن')
        page = self.open()
        self.assertContains(page, '?tab=messages&open=l')
