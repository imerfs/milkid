"""Accounting ledger rules: balanced vouchers, immutability once final, numbering, tenant isolation."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from main.accounting import ledger
from main.models import Account, Party, Voucher
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.helpers import make_municipality, make_user as _make_user


def make_user(*args, **kwargs):
    """Fresh instance: make_user changes the role with a queryset update, which a cached profile would not see."""
    return User.objects.get(pk=_make_user(*args, **kwargs).pk)


def line(account, debit=0, credit=0, **extra):
    return {'account': account, 'debit': debit, 'credit': credit, **extra}


class LedgerBase(TestCase):
    def setUp(self):
        self.dehyar = make_user('dehyari')
        self.muni = make_municipality(self.dehyar)
        self.year = ledger.open_year(self.dehyar, 1404)
        self.bank = Account.objects.create(municipality=self.muni, code='1120101', title='بانک ملی',
                                           kind='asset', nature='debit')
        self.tax = Account.objects.create(municipality=self.muni, code='5010101001', title='عوارض',
                                          kind='budget_resource', nature='credit')
        self.salary = Account.objects.create(municipality=self.muni, code='6010101001', title='حقوق دهیار',
                                             kind='budget_use', nature='debit')
        self.d = date(2025, 5, 1)  # inside 1404

    def voucher(self, amount=1000, **kw):
        return ledger.create_voucher(self.dehyar, self.year, kw.pop('on', self.d), 'income', 'عوارض',
                                     [line(self.bank, debit=amount), line(self.tax, credit=amount)], **kw)


class FiscalYearTests(LedgerBase):
    def test_year_spans_the_jalali_year(self):
        self.assertEqual(self.year.start_date, date(2025, 3, 21))
        self.assertEqual(self.year.end_date, date(2026, 3, 20))

    def test_same_year_twice_is_a_conflict(self):
        with self.assertRaises(Conflict):
            ledger.open_year(self.dehyar, 1404)

    def test_citizen_cannot_open_a_year(self):
        with self.assertRaises(Forbidden):
            ledger.open_year(make_user('citizen'), 1405)

    def test_bad_year_is_rejected(self):
        for bad in (0, 1200, 1700, 'x'):
            with self.assertRaises(Invalid):
                ledger.open_year(self.dehyar, bad)


class CreateVoucherTests(LedgerBase):
    def test_numbers_are_sequential_and_refs_unique(self):
        a, b = self.voucher(), self.voucher()
        self.assertEqual((a.number, b.number), (1, 2))
        self.assertEqual(b.ref, a.ref + 1)
        self.assertEqual(a.status, 'temporary')

    def test_unbalanced_draft_can_be_saved(self):
        v = ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=5)])
        self.assertFalse(ledger.is_balanced(v))

    def test_line_needs_exactly_one_side(self):
        for bad in (line(self.bank), line(self.bank, debit=1, credit=1)):
            with self.assertRaises(Invalid):
                ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [bad])

    def test_negative_zero_and_fractional_amounts_rejected(self):
        for bad in (-5, 0, Decimal('1.5'), 'abc', None):
            with self.assertRaises(Invalid):
                ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=bad)])
        self.assertEqual(Voucher.objects.count(), 0)

    def test_amount_over_the_column_limit_rejected(self):
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=10 ** 16)])

    def test_date_outside_year_rejected(self):
        with self.assertRaises(Invalid):
            self.voucher(on=date(2024, 1, 1))

    def test_closed_year_rejects_new_vouchers(self):
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.voucher()

    def test_party_required_account_without_party_rejected(self):
        debtors = Account.objects.create(municipality=self.muni, code='113', title='بدهکاران', kind='asset',
                                         nature='debit', requires_party=True)
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(debtors, debit=5)])

    def test_non_postable_account_rejected(self):
        group = Account.objects.create(municipality=self.muni, code='112', title='بانک‌ها', kind='asset',
                                       nature='debit', is_postable=False)
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(group, debit=5)])

    def test_description_is_required_and_bounded(self):
        for bad in ('', '   ', 'ا' * 501):
            with self.assertRaises(Invalid):
                ledger.create_voucher(self.dehyar, self.year, self.d, 'general', bad, [line(self.bank, debit=5)])

    def test_unknown_kind_rejected(self):
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'bogus', 'x', [line(self.bank, debit=5)])

    def test_failed_create_burns_no_number(self):
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=-1)])
        self.assertEqual(self.voucher().number, 1)


class FinalizeTests(LedgerBase):
    def test_balanced_voucher_can_be_finalized(self):
        v = ledger.finalize(self.dehyar, self.voucher())
        self.assertEqual(v.status, 'final')
        self.assertEqual(v.finalized_by, self.dehyar)
        self.assertIsNotNone(v.finalized_at)

    def test_unbalanced_voucher_cannot_be_finalized(self):
        v = ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x',
                                  [line(self.bank, debit=10), line(self.tax, credit=9)])
        with self.assertRaises(Conflict):
            ledger.finalize(self.dehyar, v)
        v.refresh_from_db()
        self.assertEqual(v.status, 'temporary')

    def test_single_line_voucher_cannot_be_finalized(self):
        v = ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=1)])
        with self.assertRaises(Conflict):
            ledger.finalize(self.dehyar, v)

    def test_final_voucher_is_immutable(self):
        v = ledger.finalize(self.dehyar, self.voucher())
        with self.assertRaises(Conflict):
            ledger.update_voucher(self.dehyar, v, description='y', lines=[line(self.bank, debit=1),
                                                                          line(self.tax, credit=1)])
        with self.assertRaises(Conflict):
            ledger.delete_voucher(self.dehyar, v)
        v.refresh_from_db()
        self.assertEqual(v.description, 'عوارض')

    def test_finalizing_twice_is_a_conflict(self):
        v = ledger.finalize(self.dehyar, self.voucher())
        with self.assertRaises(Conflict):
            ledger.finalize(self.dehyar, v)

    def test_only_dehyari_may_revert_and_not_in_a_closed_year(self):
        accountant = make_user('accountant', city_village=self.muni.city_village)
        v = ledger.finalize(self.dehyar, self.voucher())
        with self.assertRaises(Forbidden):
            ledger.revert_to_temporary(accountant, v)
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            ledger.revert_to_temporary(self.dehyar, v)
        self.year.is_closed = False
        self.year.save()
        self.assertEqual(ledger.revert_to_temporary(self.dehyar, v).status, 'temporary')


class UpdateAndDeleteTests(LedgerBase):
    def test_update_replaces_lines(self):
        v = self.voucher(amount=10)
        ledger.update_voucher(self.dehyar, v, description='جدید',
                              lines=[line(self.salary, debit=7), line(self.bank, credit=7)])
        v.refresh_from_db()
        self.assertEqual(v.description, 'جدید')
        self.assertEqual([(l.row, l.account.code, l.debit, l.credit) for l in v.lines.order_by('row')],
                         [(1, '6010101001', 7, 0), (2, '1120101', 0, 7)])

    def test_invalid_update_keeps_old_lines(self):
        v = self.voucher(amount=10)
        with self.assertRaises(Invalid):
            ledger.update_voucher(self.dehyar, v, description='x', lines=[line(self.bank, debit=-1)])
        self.assertEqual(v.lines.count(), 2)

    def test_delete_is_soft_and_number_not_reused(self):
        v = self.voucher()
        ledger.delete_voucher(self.dehyar, v)
        self.assertEqual(Voucher.objects.filter(pk=v.pk).count(), 1)
        self.assertIsNotNone(Voucher.objects.get(pk=v.pk).deleted_at)
        self.assertEqual(self.voucher().number, 2)
        self.assertEqual(ledger.vouchers_for(self.dehyar, self.year).count(), 1)


class TenantIsolationTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.other_dehyar = make_user('dehyari')
        self.other_muni = make_municipality(self.other_dehyar, village='روستای دیگر')
        self.other_year = ledger.open_year(self.other_dehyar, 1404)
        self.other_bank = Account.objects.create(municipality=self.other_muni, code='1120101', title='بانک',
                                                 kind='asset', nature='debit')

    def test_foreign_account_rejected(self):
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.other_bank, debit=5)])

    def test_foreign_year_and_voucher_are_not_found(self):
        with self.assertRaises(NotFound):
            ledger.create_voucher(self.other_dehyar, self.year, self.d, 'general', 'x', [line(self.other_bank, debit=5)])
        v = self.voucher()
        with self.assertRaises(NotFound):
            ledger.finalize(self.other_dehyar, v)
        with self.assertRaises(NotFound):
            ledger.get_voucher(self.other_dehyar, v.pk)

    def test_foreign_party_rejected(self):
        party = Party.objects.create(municipality=self.other_muni, kind='real', name='x', national_id='0012345679')
        debtors = Account.objects.create(municipality=self.muni, code='113', title='بدهکاران', kind='asset',
                                         nature='debit', requires_party=True)
        with self.assertRaises(Invalid):
            ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x',
                                  [line(debtors, debit=5, party=party)])

    def test_same_account_code_allowed_in_two_municipalities_but_not_twice_in_one(self):
        self.assertEqual(Account.objects.filter(code='1120101').count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Account.objects.create(municipality=self.muni, code='1120101', title='dup', kind='asset', nature='debit')

    def test_user_without_municipality_is_not_found(self):
        with self.assertRaises(NotFound):
            ledger.open_year(make_user('accountant'), 1405)


class PartyTests(LedgerBase):
    def test_valid_national_id_saves(self):
        Party(municipality=self.muni, kind='real', name='علی', national_id='0012345679').full_clean()

    def test_bad_checksum_and_repeated_digits_rejected(self):
        for bad in ('0012345678', '1111111111', '123', 'abcdefghij'):
            with self.assertRaises(ValidationError):
                Party(municipality=self.muni, kind='real', name='علی', national_id=bad).full_clean()

    def test_legal_entity_needs_eleven_digits(self):
        Party(municipality=self.muni, kind='legal', name='شرکت', national_id='10101234567').full_clean()
        with self.assertRaises(ValidationError):
            Party(municipality=self.muni, kind='legal', name='شرکت', national_id='0012345679').full_clean()

    def test_duplicate_national_id_in_one_municipality_rejected(self):
        Party.objects.create(municipality=self.muni, kind='real', name='a', national_id='0012345679')
        with self.assertRaises(ValidationError):
            Party(municipality=self.muni, kind='real', name='b', national_id='0012345679').full_clean()


class ReportTests(LedgerBase):
    def test_trial_balance_balances_and_respects_status_filter(self):
        a = ledger.finalize(self.dehyar, self.voucher(amount=100))
        self.voucher(amount=40)  # stays temporary
        rows, totals = ledger.trial_balance(self.dehyar, self.year, include_temporary=True)
        self.assertEqual(totals['debit'], totals['credit'])
        self.assertEqual(totals['debit'], 140)
        by_code = {r['code']: r for r in rows}
        self.assertEqual(by_code['1120101']['debit'], 140)
        self.assertEqual(by_code['5010101001']['credit'], 140)
        rows, totals = ledger.trial_balance(self.dehyar, self.year, include_temporary=False)
        self.assertEqual(totals['debit'], 100)
        self.assertEqual(a.status, 'final')

    def test_deleted_vouchers_are_left_out(self):
        v = self.voucher(amount=100)
        ledger.delete_voucher(self.dehyar, v)
        _, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], 0)

    def test_account_ledger_has_running_balance(self):
        self.voucher(amount=100)
        ledger.create_voucher(self.dehyar, self.year, date(2025, 5, 2), 'expense', 'حقوق',
                              [line(self.salary, debit=30), line(self.bank, credit=30)])
        rows = ledger.account_ledger(self.dehyar, self.year, self.bank)
        self.assertEqual([(r['debit'], r['credit'], r['balance']) for r in rows], [(100, 0, 100), (0, 30, 70)])
