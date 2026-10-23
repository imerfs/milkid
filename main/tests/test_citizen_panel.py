"""Citizen panel: every section opens inside the panel; a citizen only sees their own data."""
from django.test import TestCase
from django.urls import reverse

from main.models import Notification, RequestDocument, ServiceRequest
from main.tests.helpers import client_for, make_payment, make_user

PANEL = 'main:owner_dashboard'
IFRAME = {'HTTP_SEC_FETCH_DEST': 'iframe'}


def make_request(owner, title, status):
    return ServiceRequest.objects.create(user=owner, request_type='other', title=title, description='d', status=status)


def page(user, **params):
    return client_for(user).get(reverse(PANEL), params)


class OwnData(TestCase):
    def setUp(self):
        self.me, self.other = make_user('citizen'), make_user('citizen')
        make_request(self.me, 'درخواست-من', 'pending')
        make_request(self.me, 'درخواست-تمام', 'completed')
        make_request(self.other, 'درخواست-دیگری', 'pending')
        make_payment(self.me)
        make_payment(self.other)
        Notification.objects.create(user=self.me, notification_type='x', title='پیام-من', message='m')
        Notification.objects.create(user=self.other, notification_type='x', title='پیام-دیگری', message='m')
        RequestDocument.objects.create(request=self.me.service_requests.first(), document='a.pdf', document_name='مدرک-من')
        RequestDocument.objects.create(request=self.other.service_requests.first(), document='b.pdf', document_name='مدرک-دیگری')

    def test_shows_only_own_rows(self):
        html = page(self.me).content.decode()
        for mine in ('درخواست-من', 'پیام-من', 'مدرک-من'):
            self.assertIn(mine, html)
        for theirs in ('درخواست-دیگری', 'پیام-دیگری', 'مدرک-دیگری'):
            self.assertNotIn(theirs, html)

    def test_stats_are_real_counts(self):
        ctx = page(self.me).context
        self.assertEqual(ctx['stats']['active_requests'], 1)
        self.assertEqual(ctx['stats']['unpaid_payments'], 1)
        self.assertEqual(ctx['stats']['unread_notifications'], 1)

    def test_no_hardcoded_demo_data(self):
        html = page(make_user('citizen')).content.decode()
        for fake in ('عوارض سالانه ۱۴۰۳', 'پرونده #S-021', 'اطلاعیه قطعی آب'):
            self.assertNotIn(fake, html)

    def test_anonymous_is_sent_to_login(self):
        self.assertEqual(client_for().get(reverse(PANEL)).status_code, 302)


class Tabs(TestCase):
    def setUp(self):
        self.user = make_user('citizen')

    def test_default_and_unknown_tab_open_dashboard(self):
        self.assertEqual(page(self.user).context['initial_tab'], 'dashboard')
        self.assertEqual(page(self.user, tab='nope').context['initial_tab'], 'dashboard')

    def test_known_tab_deep_links(self):
        for tab in ('new-request', 'tracking', 'documents', 'payments', 'messages', 'ads', 'profile'):
            self.assertEqual(page(self.user, tab=tab).context['initial_tab'], tab)

    def test_sections_load_inside_the_panel(self):
        html = page(self.user).content.decode()
        for name in ('my_requests', 'payments_debts', 'my_property_ads', 'update_profile'):
            self.assertIn(f'data-frame-src="{reverse("main:" + name)}"', html)
        self.assertIn(f'data-frame-src="{reverse("main:messenger")}?embed=1"', html)      # chats and letters: the messenger
        self.assertIn(f'data-seg="{reverse("main:announcement_list")}"', html)

    def test_every_service_form_is_an_option_in_new_request(self):
        html = page(self.user).content.decode()
        for name in ('building_permit_form', 'without_permit_form', 'property_deed_form', 'land_use_change_form',
                     'hadi_plan_form', 'residence_confirmation_form', 'property_advertisement_form', 'create_request'):
            self.assertIn(f'data-open-frame="{reverse("main:" + name)}"', html)

    def test_sidebar_links_never_leave_the_panel(self):
        html = page(self.user).content.decode()
        nav = html.split('<nav', 1)[1].split('</nav>', 1)[0]
        self.assertNotIn('href="/', nav)


class OldUrlsDeepLink(TestCase):
    CASES = {
        'my_requests': 'tracking', 'create_request': 'new-request', 'my_property_ads': 'ads',
        'update_profile': 'profile', 'user_profile': 'profile', 'payments_debts': 'payments',
        'letters_inbox': 'messages',
    }

    def test_citizen_is_sent_to_matching_tab(self):
        for role in ('citizen', 'owner', 'resident'):
            user = make_user(role)
            for name, tab in self.CASES.items():
                r = client_for(user).get(reverse('main:' + name))
                self.assertRedirects(r, f"{reverse(PANEL)}?tab={tab}", fetch_redirect_response=False, msg_prefix=name)

    def test_page_inside_panel_frame_is_not_redirected(self):
        user = make_user('citizen')
        for name in self.CASES:
            self.assertEqual(client_for(user).get(reverse('main:' + name), **IFRAME).status_code, 200, name)
            self.assertEqual(client_for(user).get(reverse('main:' + name), {'embed': 1}).status_code, 200, name)

    def test_staff_roles_keep_old_pages(self):
        for role in ('engineer', 'accountant', 'council'):
            r = client_for(make_user(role)).get(reverse('main:my_requests'))
            self.assertEqual(r.status_code, 200, role)

    def test_post_is_never_redirected(self):
        user = make_user('citizen')
        r = client_for(user).post(reverse('main:update_profile'), {})
        self.assertEqual(r.status_code, 200)
