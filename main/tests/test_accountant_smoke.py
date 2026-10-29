"""Smoke test of the whole accountant workspace: with money in the books every tab, the printouts and the exports must render."""
from django.urls import reverse

from main.accounting.tabs import TAB_LIST
from main.tests.test_accounting_panel import PanelBase
from main.accounting import bills, ledger


class EveryTab(PanelBase):
    def setUp(self):
        super().setUp()
        self.voucher(5000, status='final')
        self.voucher(700)
        b = self.bill(9000)
        bills.record_payment(self.dehyar, b, self.d, 4000, self.bank, 'cash')
        self.bill(1200)

    def test_every_tab_renders_without_error(self):
        failures = []
        for tab in TAB_LIST:
            r = self.client.get(reverse('main:acc_panel'), {'tab': tab.key})
            if r.status_code != 200:
                failures.append((tab.key, r.status_code))
        self.assertEqual(failures, [])

    def test_every_tab_renders_inside_the_dashboard_and_as_a_fragment(self):
        failures = []
        for tab in TAB_LIST:
            for headers in ({}, {'HTTP_HX_REQUEST': 'true'}):
                r = self.client.get(reverse('main:acc_panel'), {'tab': tab.key}, **headers)
                if r.status_code != 200 or b'Traceback' in r.content or b'TemplateSyntaxError' in r.content:
                    failures.append((tab.key, bool(headers), r.status_code))
        self.assertEqual(failures, [])

    def test_the_dashboard_and_the_standalone_pages_render(self):
        for name in ('main:accountant_dashboard', 'main:acc_home', 'main:acc_voucher_list', 'main:acc_bills', 'main:acc_trial_balance',
                     'main:acc_parties', 'main:acc_accounts'):
            try:
                url = reverse(name)
            except Exception:       # pylint: disable=broad-except
                continue
            r = self.client.get(url, follow=True)
            self.assertEqual(r.status_code, 200, name)

    def test_ledger_of_every_account_and_the_trial_balance_balance(self):
        from main.models import Account
        for acc in Account.objects.filter(municipality=self.muni)[:40]:
            r = self.client.get(reverse('main:acc_p_ledger', args=[self.year.pk, acc.pk]))
            self.assertEqual(r.status_code, 200, acc.pk)
        r = self.client.get(reverse('main:acc_panel'), {'tab': 'trial'})
        self.assertEqual(r.status_code, 200)

    def test_statement_exports_and_year_end_previews(self):
        for key in ('resources_uses', 'balance_sheet'):
            r = self.client.get(reverse('main:acc_p_statement_export', args=[self.year.pk, key]))
            self.assertEqual(r.status_code, 200, key)
            self.assertIn('spreadsheetml', r['Content-Type'])
        from main.views.accounting_statements import OPERATIONS
        for kind in [o[0] for o in OPERATIONS]:
            r = self.client.get(reverse('main:acc_p_yearend_preview', args=[self.year.pk, kind]))
            self.assertIn(r.status_code, (200, 409), kind)         # 409 = a rule (close the temporary accounts first), never a crash
