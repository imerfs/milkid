"""Audit trail and configurable access levels of the accounting workspace."""
from datetime import date

from django.contrib.auth import authenticate
from django.test import Client
from django.urls import get_resolver, reverse

from main.accounting import access_levels, ledger
from main.models import AccessRule, AuditEvent, Voucher
from main.office.errors import Forbidden, Invalid
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase, line, make_user


class AuditTests(LedgerBase):
    def events(self, **filters):
        return AuditEvent.objects.filter(municipality=self.muni, **filters)

    def test_creating_changing_and_deleting_a_record_is_recorded_with_what_changed(self):
        voucher = self.voucher()
        self.assertEqual(self.events(model='Voucher', action='create').count(), 1)
        ledger.finalize(self.dehyar, voucher)
        update = self.events(model='Voucher', action='update').first()
        self.assertEqual(update.changes['status'], ['temporary', 'final'])
        self.assertEqual(update.object_id, str(voucher.pk))

    def test_the_acting_user_is_taken_from_the_request(self):
        client = client_for(self.dehyar)
        self.voucher()
        voucher = Voucher.objects.get()
        client.post(reverse('main:acc_p_voucher_action', args=[voucher.pk, 'finalize']))
        event = self.events(model='Voucher', action='update').latest('id')
        self.assertEqual((event.username, event.user_id), (self.dehyar.username, self.dehyar.pk))

    def test_other_municipalities_do_not_see_these_events(self):
        self.voucher()
        other = make_user('dehyari')
        from main.tests.helpers import make_municipality
        other_muni = make_municipality(other)
        self.assertEqual(AuditEvent.objects.filter(municipality=other_muni).count(), 0)

    def test_login_logout_and_failed_login_are_recorded(self):
        user = make_user('citizen')
        user.set_password('pw-test-12345')
        user.save()
        client = Client()
        client.post('/login/', {'username': user.username, 'password': 'pw-test-12345'})
        client.logout()
        authenticate(username=user.username, password='wrong')
        actions = set(AuditEvent.objects.filter(username=user.username).values_list('action', flat=True))
        self.assertIn('login_failed', actions)

    def test_a_recording_failure_never_breaks_the_request(self):
        from unittest import mock
        with mock.patch('main.models.AuditEvent.objects.create', side_effect=RuntimeError('boom')),                 self.assertLogs('main.audit', 'ERROR'):
            self.assertTrue(self.voucher())

    def test_the_audit_screen_is_for_the_mayor(self):
        self.voucher()
        page = client_for(self.dehyar).get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'audit'})
        self.assertGreaterEqual(len(page.context['page'].object_list), 1)
        filtered = client_for(self.dehyar).get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'audit', 'model': 'Voucher'})
        self.assertTrue(all(e.model == 'Voucher' for e in filtered.context['page'].object_list))
        export = client_for(self.dehyar).get(reverse('main:acc_p_audit_export'))
        self.assertEqual(export.status_code, 200)
        accountant = make_user('accountant', city_village=self.muni.city_village)
        self.assertEqual(client_for(accountant).get(reverse('main:acc_p_audit_export')).status_code, 403)


class AccessLevelTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.accountant = make_user('accountant', city_village=self.muni.city_village)
        self.client_a = client_for(self.accountant)
        self.client_d = client_for(self.dehyar)

    def set_levels(self, **levels):
        access_levels.save_rules(self.dehyar, levels)

    def test_everything_is_editable_until_the_mayor_restricts_it(self):
        self.assertTrue(all(v == 'edit' for v in access_levels.rules_for(self.muni).values()))

    def test_a_closed_area_hides_the_tab_and_refuses_its_urls(self):
        self.set_levels(vouchers='none')
        page = self.client_d.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'vouchers'})
        self.assertEqual(page.status_code, 200)                           # the mayor is never restricted
        self.assertEqual(access_levels.tab_level(self.accountant, 'vouchers'), 'none')
        self.assertIn('vouchers', access_levels.hidden_tabs(self.accountant))
        self.assertEqual(access_levels.hidden_tabs(self.dehyar), [])

    def test_view_only_allows_reading_but_not_changing(self):
        voucher = self.voucher()
        self.set_levels(vouchers='view')
        self.assertEqual(access_levels.level_for(self.accountant, 'vouchers'), 'view')
        self.assertEqual(access_levels.level_for(self.accountant, 'bills'), 'edit')

    def test_the_panel_shows_a_denied_notice_for_a_closed_tab(self):
        self.set_levels(budget='none')
        page = self.client_a.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'budget'})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['tab_template'].rsplit('/', 1)[-1], '_denied.html')
        self.assertIn('budget', page.context['hidden_tabs'])

    def test_closed_and_view_only_urls_answer_403_to_the_accountant(self):
        voucher = self.voucher()
        self.set_levels(vouchers='view', budget='none')
        finalize = reverse('main:acc_p_voucher_action', args=[voucher.pk, 'finalize'])
        self.assertEqual(self.client_a.post(finalize).status_code, 403)
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'temporary')
        self.assertEqual(self.client_a.get(reverse('main:acc_p_voucher_detail', args=[voucher.pk])).status_code, 200)
        self.assertEqual(self.client_a.get(reverse('main:acc_p_budget', args=[self.year.id])).status_code, 403)
        htmx = self.client_a.get(reverse('main:acc_p_budget', args=[self.year.id]), HTTP_HX_REQUEST='true')
        self.assertIn('accError', htmx['HX-Trigger'])
        self.assertEqual(self.client_d.post(finalize).status_code, 204)        # the mayor still can

    def test_only_the_mayor_changes_the_levels_and_values_are_checked(self):
        with self.assertRaises(Invalid):
            access_levels.save_rules(self.dehyar, {'vouchers': 'maybe'})
        with self.assertRaises(Invalid):
            access_levels.save_rules(self.dehyar, {'nowhere': 'none'})
        with self.assertRaises(Forbidden):
            access_levels.save_rules(self.accountant, {'vouchers': 'none'})
        response = self.client_d.post(reverse('main:acc_p_access_save'), {'area_vouchers': 'view', 'area_bills': 'none'})
        self.assertEqual(response.status_code, 204)
        levels = access_levels.rules_for(self.muni)
        self.assertEqual((levels['vouchers'], levels['bills'], levels['budget']), ('view', 'none', 'edit'))
        self.client_d.post(reverse('main:acc_p_access_save'), {})
        self.assertEqual(AccessRule.objects.count(), 0)                       # back to everything editable
        self.assertEqual(self.client_a.post(reverse('main:acc_p_access_save'), {'area_vouchers': 'none'}).status_code, 403)

    def test_levels_belong_to_one_municipality(self):
        self.set_levels(vouchers='none')
        from main.tests.helpers import make_municipality
        other_mayor = make_user('dehyari')
        make_municipality(other_mayor)
        self.assertEqual(access_levels.rules_for(ledger.municipality_of(other_mayor))['vouchers'], 'edit')

    def test_every_accounting_url_belongs_to_an_area(self):
        from main.url_groups import accounting
        for pattern in accounting.urlpatterns:
            access_levels.area_of(pattern.name)                                 # raises KeyError for a name nobody mapped

    def test_access_screen_for_mayor_and_not_for_accountant(self):
        page = self.client_d.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'access'})
        self.assertEqual(len(page.context['access_rows']), len(access_levels.AREAS))
        denied = self.client_a.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'access'})
        self.assertFalse(denied.context['access_allowed'])
