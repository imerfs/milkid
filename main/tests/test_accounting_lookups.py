"""Financial settings: cost centers (with in-use protection), standard descriptions, signatories."""
from main.accounting import ledger, lookups
from main.models import CostCenter, Party
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.helpers import make_municipality
from main.tests.test_accounting_ledger import LedgerBase, line, make_user


class LookupTests(LedgerBase):
    def test_cost_center_unique_code_and_delete(self):
        c = lookups.add_cost_center(self.dehyar, '1', 'مالی')
        with self.assertRaises(Conflict):
            lookups.add_cost_center(self.dehyar, '1', 'دیگر')
        lookups.delete_cost_center(self.dehyar, c)
        self.assertFalse(CostCenter.objects.exists())

    def test_cost_center_in_use_cannot_be_deleted(self):
        c = lookups.add_cost_center(self.dehyar, '2', 'اداری')
        ledger.create_voucher(self.dehyar, self.year, self.d, 'expense', 'x', [
            line(self.salary, debit=5, cost_center=c), line(self.bank, credit=5)])
        with self.assertRaises(Conflict):
            lookups.delete_cost_center(self.dehyar, c)

    def test_descriptions_and_signatories(self):
        lookups.add_description(self.dehyar, 'voucher', '1', 'دریافت وجه')
        lookups.add_description(self.dehyar, 'account', '1', 'همان کد، نوع دیگر')   # same code, other kind is fine
        with self.assertRaises(Conflict):
            lookups.add_description(self.dehyar, 'voucher', '1', 'تکراری')
        with self.assertRaises(Invalid):
            lookups.add_description(self.dehyar, 'x', '2', 'a')
        s = lookups.add_signatory(self.dehyar, 'علی', 'دهیار')
        with self.assertRaises(Conflict):
            lookups.add_signatory(self.dehyar, 'علی', 'دهیار')
        lookups.delete_signatory(self.dehyar, s)
        self.assertEqual(lookups.signatories(self.dehyar).count(), 0)
        for bad in ('', ' '):
            with self.assertRaises(Invalid):
                lookups.add_signatory(self.dehyar, bad, 'x')

    def test_tenant_isolation(self):
        c = lookups.add_cost_center(self.dehyar, '9', 'x')
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        with self.assertRaises(NotFound):
            lookups.delete_cost_center(other, c)
        self.assertEqual(lookups.cost_centers(other).count(), 0)
        with self.assertRaises(Forbidden):
            lookups.add_cost_center(make_user('citizen'), '1', 'x')
