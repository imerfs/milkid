"""Date lock, data integrity check and bank reconciliation."""
from datetime import date

from django.urls import reverse

from main.accounting import bills, controls, integrity, ledger
from main.models import Account, Party, ReconMark, Voucher, VoucherLine
from main.office.errors import Conflict, Forbidden, Invalid
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase, line, make_user


class LockTests(LedgerBase):
    def lock(self, on=date(2025, 6, 30)):
        return controls.set_lock(self.dehyar, on)

    def test_vouchers_on_or_before_the_lock_date_cannot_be_created(self):
        self.lock()
        for on in (date(2025, 6, 30), date(2025, 4, 1)):
            with self.assertRaises(Conflict):
                self.voucher(on=on)
        self.assertTrue(self.voucher(on=date(2025, 7, 1)))

    def test_locked_vouchers_cannot_be_edited_finalized_reverted_or_deleted(self):
        draft, final = self.voucher(on=date(2025, 5, 1)), self.voucher(on=date(2025, 5, 2))
        ledger.finalize(self.dehyar, final)
        self.lock()
        with self.assertRaises(Conflict):
            ledger.update_voucher(self.dehyar, draft, description='x', lines=[line(self.bank, debit=1), line(self.tax, credit=1)])
        with self.assertRaises(Conflict):
            ledger.finalize(self.dehyar, draft)
        with self.assertRaises(Conflict):
            ledger.revert_to_temporary(self.dehyar, final)
        with self.assertRaises(Conflict):
            ledger.delete_voucher(self.dehyar, draft)

    def test_a_voucher_cannot_be_moved_into_the_locked_period(self):
        draft = self.voucher(on=date(2025, 8, 1))
        self.lock()
        with self.assertRaises(Conflict):
            ledger.update_voucher(self.dehyar, draft, description='x', on=date(2025, 5, 1),
                                  lines=[line(self.bank, debit=1), line(self.tax, credit=1)])

    def test_lifting_the_lock_allows_changes_again(self):
        self.lock()
        controls.set_lock(self.dehyar, None)
        self.assertTrue(self.voucher(on=date(2025, 5, 1)))

    def test_only_the_mayor_changes_the_lock(self):
        accountant = make_user('accountant')
        accountant.profile.city_village = self.dehyar.profile.city_village
        with self.assertRaises((Forbidden, Exception)):
            controls.set_lock(accountant, date(2025, 6, 30))

    def test_the_lock_is_per_municipality(self):
        self.lock()
        other_mayor = make_user('dehyari')
        from main.tests.helpers import make_municipality
        make_municipality(other_mayor)
        other_year = ledger.open_year(other_mayor, 1404)
        other_bank = Account.objects.create(municipality=other_year.municipality, code='1', title='b', kind='asset', nature='debit')
        other_tax = Account.objects.create(municipality=other_year.municipality, code='2', title='t', kind='budget_resource', nature='credit')
        self.assertTrue(ledger.create_voucher(other_mayor, other_year, date(2025, 5, 1), 'income', 'x',
                                              [line(other_bank, debit=5), line(other_tax, credit=5)]))

    def test_bill_payments_follow_the_lock(self):
        party = Party.objects.create(municipality=self.muni, name='پرداخت‌کننده')
        bill = bills.issue_bill(self.dehyar, self.year, date(2025, 5, 1), party, self.tax, 1000, 'عوارض')
        payment = bills.record_payment(self.dehyar, bill, date(2025, 5, 2), 400, self.bank, 'cash')
        self.lock()
        with self.assertRaises(Conflict):
            bills.cancel_payment(self.dehyar, payment)
        with self.assertRaises(Conflict):
            bills.issue_bill(self.dehyar, self.year, date(2025, 5, 3), party, self.tax, 10, 'دیگر')


class IntegrityTests(LedgerBase):
    def failed(self, results):
        return {r['key'] for r in results if r['count']}

    def test_a_clean_ledger_passes(self):
        self.voucher()
        self.assertEqual(self.failed(integrity.run(self.dehyar, self.year)), set())

    def test_unbalanced_and_out_of_year_vouchers_are_found(self):
        ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'ناقص', [line(self.bank, debit=5)])
        voucher = self.voucher()
        Voucher.objects.filter(pk=voucher.pk).update(date=date(2020, 1, 1))
        results = {r['key']: r for r in integrity.run(self.dehyar, self.year)}
        self.assertEqual(results['unbalanced']['count'], 1)
        self.assertEqual(results['out_of_year']['count'], 1)
        self.assertEqual(results['trial_gap']['count'], 1)

    def test_missing_party_and_group_account_lines_are_found(self):
        self.voucher()
        self.bank.requires_party = True
        self.bank.save()
        self.tax.is_postable = False
        self.tax.save()
        failed = self.failed(integrity.run(self.dehyar, self.year))
        self.assertTrue({'no_party', 'not_postable'} <= failed)

    def test_payment_with_a_changed_voucher_is_found(self):
        party = Party.objects.create(municipality=self.muni, name='ب')
        bill = bills.issue_bill(self.dehyar, self.year, self.d, party, self.tax, 1000, 'عوارض')
        payment = bills.record_payment(self.dehyar, bill, self.d, 400, self.bank, 'cash')
        VoucherLine.objects.filter(voucher=payment.voucher, debit__gt=0).update(debit=300)
        self.assertIn('payment_voucher', self.failed(integrity.run(self.dehyar, self.year)))

    def test_only_this_municipalitys_rows_are_examined(self):
        other_mayor = make_user('dehyari')
        from main.tests.helpers import make_municipality
        other_muni = make_municipality(other_mayor)
        other_year = ledger.open_year(other_mayor, 1404)
        other_bank = Account.objects.create(municipality=other_muni, code='1', title='b', kind='asset', nature='debit')
        ledger.create_voucher(other_mayor, other_year, self.d, 'general', 'ناقص', [line(other_bank, debit=5)])
        self.assertEqual(self.failed(integrity.run(self.dehyar)), set())


class ReconciliationTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.v1, self.v2 = self.voucher(1000), self.voucher(500, on=date(2025, 6, 1))
        ledger.create_voucher(self.dehyar, self.year, date(2025, 7, 1), 'expense', 'هزینه',
                              [line(self.salary, debit=200), line(self.bank, credit=200)])

    def bank_line(self, voucher):
        return voucher.lines.get(account=self.bank)

    def test_balances_split_into_ticked_and_unticked(self):
        data = controls.reconciliation(self.dehyar, self.year, self.bank)
        self.assertEqual((data['book'], data['cleared'], data['uncleared']), (1300, 0, 1300))
        controls.save_marks(self.dehyar, self.year, self.bank, [r['line'].id for r in data['rows']],
                            [self.bank_line(self.v1).id])
        data = controls.reconciliation(self.dehyar, self.year, self.bank, statement_balance=1000)
        self.assertEqual((data['cleared'], data['uncleared'], data['difference']), (1000, 300, 0))
        self.assertEqual([r['marked'] for r in data['rows']], [True, False, False])

    def test_unticking_and_the_date_range(self):
        all_ids = [r['line'].id for r in controls.reconciliation(self.dehyar, self.year, self.bank)['rows']]
        controls.save_marks(self.dehyar, self.year, self.bank, all_ids, all_ids)
        controls.save_marks(self.dehyar, self.year, self.bank, all_ids[:1], [])
        self.assertEqual(ReconMark.objects.count(), 2)
        data = controls.reconciliation(self.dehyar, self.year, self.bank, date_from=date(2025, 6, 1), date_to=date(2025, 6, 30))
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['book'], 1500)                           # the balance counts everything up to the end date

    def test_only_bank_and_cash_accounts_and_own_lines(self):
        with self.assertRaises(Invalid):
            controls.reconciliation(self.dehyar, self.year, self.tax)
        with self.assertRaises(Invalid):
            controls.save_marks(self.dehyar, self.year, self.bank, [self.v1.lines.get(account=self.tax).id], [])

    def test_the_panel_tabs_and_the_save_endpoint(self):
        client = client_for(self.dehyar)
        tab = lambda name, **p: client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': name, **p})
        self.assertContains(tab('recon'), 'حساب بانک')
        page = tab('recon', account=self.bank.id, statement='1000')
        self.assertEqual(len(page.context['recon']['rows']), 3)
        shown = page.context['shown_ids']
        done = client.post(reverse('main:acc_p_recon_save', args=[self.year.id]),
                           {'account': self.bank.id, 'shown': shown, 'line': [self.bank_line(self.v1).id]})
        self.assertEqual(done.status_code, 204)
        self.assertEqual(ReconMark.objects.count(), 1)
        self.assertContains(tab('recon', date_from='x', account=self.bank.id), 'تاریخ')
        controls_tab = tab('controls')
        self.assertContains(controls_tab, 'قفل تاریخ')
        self.assertEqual(controls_tab.context['check_summary']['failed'], 0)
        locked = client.post(reverse('main:acc_p_lock_set'), {'lock_date': '1404/03/31'})
        self.assertEqual(locked.status_code, 204)
        self.assertEqual(controls.get_lock(self.dehyar).lock_date, date(2025, 6, 21))
        self.assertEqual(client.post(reverse('main:acc_p_lock_set'), {'lock_date': 'x'}).status_code, 400)
