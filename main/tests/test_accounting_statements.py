"""Financial statements, multi-level trial balance and the year-end operations (closing and opening vouchers)."""
from datetime import date

from django.urls import reverse

from main.accounting import ledger, statements, yearend
from main.models import Account, Voucher
from main.office.errors import Conflict, Invalid
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase, line


class YearEndBase(LedgerBase):
    def setUp(self):
        super().setUp()
        def make(code, title, kind, nature):
            return Account.objects.create(municipality=self.muni, code=code, title=title, kind=kind, nature=nature)

        self.a111 = make('111', 'افتتاحیه', 'asset', 'debit')
        self.a410 = make('410', 'مازاد / کسری', 'equity', 'credit')
        self.a411 = make('411', 'اختتامیه', 'closing', 'credit')
        self.group = Account.objects.create(municipality=self.muni, code='501', title='منابع درآمدی', kind='budget_resource',
                                            nature='credit', is_postable=False)
        self.tax.parent = self.group
        self.tax.save()
        # 1000 comes in, 300 goes out: surplus 700, the bank holds 700
        self.voucher(1000)
        ledger.create_voucher(self.dehyar, self.year, self.d, 'expense', 'حقوق',
                              [line(self.salary, debit=300), line(self.bank, credit=300)])

    def finalize_all(self, year=None):
        for v in Voucher.objects.filter(fiscal_year=year or self.year, deleted_at__isnull=True, status='temporary'):
            ledger.finalize(self.dehyar, v)


class StatementTests(YearEndBase):
    def test_resources_and_uses_with_group_subtotal_and_surplus(self):
        data = statements.resources_and_uses(self.dehyar, self.year)
        self.assertEqual((data['resources']['total'], data['uses']['total'], data['surplus']), (1000, 300, 700))
        codes = [r['code'] for r in data['resources']['rows']]
        self.assertEqual(codes, ['501', '5010101001'])                    # the group shows the sum of its accounts
        self.assertEqual(data['resources']['rows'][0]['amount'], 1000)
        self.assertFalse(data['resources']['rows'][0]['leaf'])

    def test_statements_can_be_cut_at_a_date_and_to_final_vouchers(self):
        ledger.create_voucher(self.dehyar, self.year, date(2025, 9, 1), 'income', 'دیرتر',
                              [line(self.bank, debit=50), line(self.tax, credit=50)])
        self.assertEqual(statements.resources_and_uses(self.dehyar, self.year)['resources']['total'], 1050)
        self.assertEqual(statements.resources_and_uses(self.dehyar, self.year, upto=date(2025, 6, 1))['resources']['total'], 1000)
        self.assertEqual(statements.resources_and_uses(self.dehyar, self.year, final_only=True)['resources']['total'], 0)

    def test_balance_sheet_balances_with_the_open_surplus(self):
        sheet = statements.balance_sheet(self.dehyar, self.year)
        self.assertEqual((sheet['total_assets'], sheet['surplus'], sheet['difference']), (700, 700, 0))
        self.assertEqual([r['code'] for r in sheet['assets']], ['1120101'])

    def test_a_clearing_account_with_a_balance_is_reported(self):
        ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'دستی',
                              [line(self.a111, debit=10), line(self.bank, credit=10)])
        sheet = statements.balance_sheet(self.dehyar, self.year)
        self.assertEqual([c['code'] for c in sheet['clearing']], ['111'])

    def test_other_municipalities_are_refused(self):
        from main.tests.test_accounting_ledger import make_user
        with self.assertRaises(Exception):
            statements.balance_sheet(make_user('citizen'), self.year)


class TrialByLevelTests(YearEndBase):
    def test_detail_level_has_opening_turnover_and_ending(self):
        rows, totals = statements.trial_by_level(self.dehyar, self.year)
        bank = next(r for r in rows if r['code'] == '1120101')
        self.assertEqual((bank['open_d'], bank['turn_d'], bank['turn_c'], bank['end_d']), (0, 1000, 300, 700))
        self.assertEqual((totals['debit'], totals['credit']), (1300, 1300))

    def test_levels_roll_accounts_up_to_their_group(self):
        rows, _ = statements.trial_by_level(self.dehyar, self.year, level='1')
        by_code = {r['code']: r for r in rows}
        self.assertIn('501', by_code)
        self.assertNotIn('5010101001', by_code)
        self.assertEqual(by_code['501']['turn_c'], 1000)

    def test_date_range_moves_earlier_turnover_into_the_opening(self):
        ledger.create_voucher(self.dehyar, self.year, date(2025, 9, 1), 'income', 'دیرتر',
                              [line(self.bank, debit=50), line(self.tax, credit=50)])
        rows, _ = statements.trial_by_level(self.dehyar, self.year, date_from=date(2025, 8, 1))
        bank = next(r for r in rows if r['code'] == '1120101')
        self.assertEqual((bank['open_d'], bank['turn_d'], bank['end_d']), (700, 50, 750))

    def test_bad_level_is_refused(self):
        with self.assertRaises(Invalid):
            statements.trial_by_level(self.dehyar, self.year, level='9')

    def test_ledger_of_a_group_account_lists_its_accounts_and_the_carried_balance(self):
        rows = ledger.account_ledger(self.dehyar, self.year, self.group)
        self.assertEqual([r['credit'] for r in rows], [1000])
        self.assertEqual(rows[0]['account'], self.tax)
        rows = ledger.account_ledger(self.dehyar, self.year, self.bank, date_from=date(2025, 8, 1))
        self.assertEqual((rows[0]['voucher'], rows[0]['balance']), (None, 700))


class YearEndTests(YearEndBase):
    def test_temporary_closing_zeroes_resources_and_uses_against_410(self):
        data = yearend.plan(self.dehyar, self.year, 'temp_closing')
        self.assertEqual((data['debit'], data['credit']), (1000, 1000))
        voucher = yearend.issue(self.dehyar, self.year, 'temp_closing')
        self.assertEqual((voucher.kind, voucher.status, voucher.date), ('temp_closing', 'temporary', self.year.end_date))
        by_account = {ln.account.code: (ln.debit, ln.credit) for ln in voucher.lines.all()}
        self.assertEqual(by_account, {'5010101001': (1000, 0), '6010101001': (0, 300), '410': (0, 700)})
        # the statement of resources and uses still shows the year; the balance sheet now carries the surplus as equity
        self.assertEqual(statements.resources_and_uses(self.dehyar, self.year)['surplus'], 700)
        sheet = statements.balance_sheet(self.dehyar, self.year)
        self.assertEqual((sheet['surplus'], sheet['total_assets'], sheet['difference']), (0, 700, 0))
        self.assertEqual([r['amount'] for r in sheet['claims'] if r['code'] == '410'], [700])

    def test_issuing_again_replaces_a_temporary_voucher_but_not_a_final_one(self):
        first = yearend.issue(self.dehyar, self.year, 'temp_closing')
        second = yearend.issue(self.dehyar, self.year, 'temp_closing')
        first.refresh_from_db()
        self.assertIsNotNone(first.deleted_at)
        self.assertEqual(Voucher.objects.filter(fiscal_year=self.year, kind='temp_closing', deleted_at__isnull=True).count(), 1)
        ledger.finalize(self.dehyar, second)
        with self.assertRaises(Conflict):
            yearend.issue(self.dehyar, self.year, 'temp_closing')

    def test_closing_voucher_needs_the_temporary_accounts_closed_first(self):
        with self.assertRaises(Conflict):
            yearend.plan(self.dehyar, self.year, 'closing')
        yearend.issue(self.dehyar, self.year, 'temp_closing')
        data = yearend.plan(self.dehyar, self.year, 'closing')
        by_account = {}
        for ln in data['lines']:
            by_account.setdefault(ln['account'].code, []).append((ln['debit'], ln['credit']))
        self.assertEqual(by_account['1120101'], [(0, 700)])
        self.assertEqual(by_account['410'], [(700, 0)])
        self.assertEqual(sorted(by_account['411']), [(0, 700), (700, 0)])          # the clearing account shows both halves and nets to zero
        self.assertEqual((data['debit'], data['credit']), (1400, 1400))

    def test_opening_voucher_carries_the_balances_into_the_next_year(self):
        yearend.issue(self.dehyar, self.year, 'temp_closing')
        yearend.issue(self.dehyar, self.year, 'closing')
        self.finalize_all()
        next_year = ledger.open_year(self.dehyar, 1405)
        voucher = yearend.issue(self.dehyar, next_year, 'opening')
        self.assertEqual((voucher.kind, voucher.date), ('opening', next_year.start_date))
        carried = {ln.account.code: (ln.debit, ln.credit) for ln in voucher.lines.all() if ln.account.code not in ('111',)}
        self.assertEqual(carried, {'1120101': (700, 0), '410': (0, 700)})
        self.finalize_all(next_year)
        rows, totals = statements.trial_by_level(self.dehyar, next_year)
        bank = next(r for r in rows if r['code'] == '1120101')
        self.assertEqual((bank['open_d'], bank['end_d']), (700, 700))
        self.assertEqual(statements.balance_sheet(self.dehyar, next_year)['difference'], 0)

    def test_opening_needs_the_previous_year_and_closed_temporary_accounts(self):
        with self.assertRaises(Conflict):
            yearend.plan(self.dehyar, self.year, 'opening')                  # no 1403
        next_year = ledger.open_year(self.dehyar, 1405)
        with self.assertRaises(Conflict):
            yearend.plan(self.dehyar, next_year, 'opening')                  # 1404 temporary accounts still open

    def test_unbalanced_vouchers_block_issuing(self):
        ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'ناقص', [line(self.bank, debit=5)])
        with self.assertRaises(Conflict):
            yearend.issue(self.dehyar, self.year, 'temp_closing')

    def test_a_missing_clearing_account_is_explained(self):
        self.a410.delete()
        with self.assertRaises(Invalid):
            yearend.plan(self.dehyar, self.year, 'temp_closing')

    def test_closing_the_year_needs_final_vouchers_and_blocks_new_ones(self):
        with self.assertRaises(Conflict):
            yearend.close_year(self.dehyar, self.year)
        self.finalize_all()
        yearend.close_year(self.dehyar, self.year)
        with self.assertRaises(Conflict):
            self.voucher()
        yearend.reopen_year(self.dehyar, self.year)
        self.assertTrue(self.voucher())

    def test_only_the_mayor_reopens_a_closed_year(self):
        from main.tests.test_accounting_ledger import make_user
        self.finalize_all()
        yearend.close_year(self.dehyar, self.year)
        accountant = make_user('accountant')
        accountant.profile.city_village = self.dehyar.profile.city_village
        with self.assertRaises(Exception):
            yearend.reopen_year(accountant, self.year)


class PanelTests(YearEndBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def tab(self, tab, **params):
        return self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': tab, **params})

    def test_statements_tab_and_export(self):
        page = self.tab('statements')
        self.assertContains(page, 'جمع منابع')
        self.assertEqual(page.context['statement']['surplus'], 700)
        sheet = self.tab('statements', statement='balance_sheet')
        self.assertEqual(sheet.context['statement']['difference'], 0)
        bad = self.tab('statements', upto='x')
        self.assertContains(bad, 'تاریخ')
        export = self.client.get(reverse('main:acc_p_statement_export', args=[self.year.id, 'balance_sheet']))
        self.assertEqual(export.status_code, 200)
        self.assertEqual(self.client.get(reverse('main:acc_p_statement_export', args=[self.year.id, 'nope'])).status_code, 400)

    def test_trial_tab_levels(self):
        page = self.tab('trial', level='1')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['level'], '1')
        self.assertContains(self.tab('trial', level='1', date_from='x'), 'تاریخ')

    def test_yearend_tab_preview_issue_and_close(self):
        self.assertContains(self.tab('yearend'), 'سند اختتامیه')
        preview = self.client.get(reverse('main:acc_p_yearend_preview', args=[self.year.id, 'temp_closing']))
        self.assertContains(preview, 'صدور سند')
        done = self.client.post(reverse('main:acc_p_yearend_issue', args=[self.year.id, 'temp_closing']))
        self.assertEqual(done.status_code, 204)
        self.assertTrue(Voucher.objects.filter(fiscal_year=self.year, kind='temp_closing').exists())
        failed = self.client.post(reverse('main:acc_p_year_close', args=[self.year.id]))
        self.assertEqual(failed.status_code, 409)                      # still temporary vouchers
        self.assertEqual(self.client.get(reverse('main:acc_p_yearend_issue', args=[self.year.id, 'closing'])).status_code, 405)

    def test_citizens_cannot_use_year_end_screens(self):
        from main.tests.helpers import make_user
        other = client_for(make_user('citizen'))
        for name, args in (('acc_p_yearend_preview', [self.year.id, 'closing']), ('acc_p_statement_export', [self.year.id, 'balance_sheet'])):
            self.assertIn(other.get(reverse(f'main:{name}', args=args)).status_code, (302, 403))
