"""Reports: filters, totals, running balances, tenant isolation, bad input."""
from datetime import date

from main.accounting import contracts, reports
from main.models import CostCenter, Party
from main.office.errors import Forbidden, Invalid, NotFound
from main.tests.helpers import make_municipality
from main.tests.test_accounting_ledger import LedgerBase, line, make_user


class ReportBase(LedgerBase):
    def rep(self, key, **params):
        return reports.run(self.dehyar, self.year, key, params)


class VoucherReportTests(ReportBase):
    def test_list_totals_and_filters(self):
        self.voucher(300)
        v2 = self.voucher(700, on=date(2025, 6, 1))
        from main.accounting import ledger
        ledger.finalize(self.dehyar, v2)
        out = self.rep('vouchers')
        self.assertEqual([r[0] for r in out['rows']], [1, 2])
        self.assertEqual(out['totals'][6:], [1000, 1000])
        self.assertEqual(len(self.rep('vouchers', status='final')['rows']), 1)
        self.assertEqual(len(self.rep('vouchers', date_from='۱۴۰۴/۰۳/۱۱')['rows']), 1)   # 2025-06-01
        self.assertEqual(len(self.rep('vouchers', number_from='2', number_to='2')['rows']), 1)
        self.assertEqual(len(self.rep('vouchers', q='عوارض')['rows']), 2)
        self.assertEqual(len(self.rep('vouchers', q='چیز دیگر')['rows']), 0)

    def test_bad_date_is_invalid(self):
        with self.assertRaises(Invalid):
            self.rep('vouchers', date_from='not a date')

    def test_unknown_report(self):
        with self.assertRaises(NotFound):
            self.rep('nope')


class LedgerReportTests(ReportBase):
    def test_party_ledger_running_balance(self):
        party = Party.objects.create(municipality=self.muni, name='علی')
        from main.accounting import ledger
        ledger.create_voucher(self.dehyar, self.year, self.d, 'income', 'الف', [
            line(self.bank, debit=500, party=party), line(self.tax, credit=500)])
        ledger.create_voucher(self.dehyar, self.year, self.d, 'income', 'ب', [
            line(self.bank, credit=200, party=party), line(self.tax, debit=200)])
        out = self.rep('party_ledger', party=party.id)
        self.assertEqual([r[-1] for r in out['rows']], [500, 300])
        with self.assertRaises(Invalid):
            self.rep('party_ledger')
        other = make_user('dehyari')
        foreign = Party.objects.create(municipality=make_municipality(other, village='x'), name='y')
        with self.assertRaises(Invalid):
            self.rep('party_ledger', party=foreign.id)

    def test_cost_center_and_journal(self):
        center = CostCenter.objects.create(municipality=self.muni, code='1', title='مالی')
        from main.accounting import ledger
        ledger.create_voucher(self.dehyar, self.year, self.d, 'expense', 'هزینه', [
            line(self.salary, debit=90, cost_center=center), line(self.bank, credit=90)])
        self.assertEqual(self.rep('cost_center', cost_center=center.id)['rows'][0][4], 90)
        out = self.rep('journal')
        self.assertEqual(len(out['rows']), 2)
        self.assertEqual(out['totals'][5:], [90, 90])


class OtherReportTests(ReportBase):
    def test_every_report_runs_on_empty_data(self):
        for key in reports.REPORTS:
            if key in ('party_ledger', 'cost_center'):
                continue
            out = self.rep(key)
            self.assertEqual(out['rows'], [], key)
            self.assertIsNone(out['totals'])

    def test_contracts_report(self):
        party = Party.objects.create(municipality=self.muni, name='پ')
        c = contracts.create_contract(self.dehyar, self.year, subject='کار', contractor=party, date=self.d, start_date=self.d,
                                      end_date=date(2025, 12, 1), amount=1000)
        contracts.add_statement(self.dehyar, c, self.d, 400)
        row = self.rep('contracts')['rows'][0]
        self.assertEqual((row[3], row[4]), (1000, 400))

    def test_other_tenant_and_citizen(self):
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        with self.assertRaises(NotFound):
            reports.run(other, self.year, 'vouchers', {})
        with self.assertRaises(Forbidden):
            reports.run(make_user('citizen'), self.year, 'vouchers', {})
