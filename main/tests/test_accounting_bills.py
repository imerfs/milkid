"""Cash bills and their payments: each payment posts an income voucher; paid never exceeds the bill."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.db import IntegrityError, transaction
from django.urls import reverse

from main.accounting import bills, ledger
from main.models import Bill, BillPayment, Party
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.helpers import client_for, make_municipality
from main.tests.test_accounting_ledger import LedgerBase, make_user


class BillBase(LedgerBase):
    def setUp(self):
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='علی رضایی', national_id='0499370899')

    def bill(self, amount=1000, **kw):
        return bills.issue_bill(self.dehyar, self.year, kw.pop('on', self.d), self.party, self.tax, amount,
                                kw.pop('description', 'عوارض نوسازی'))

    def pay(self, bill, amount, **kw):
        return bills.record_payment(self.dehyar, bill, kw.pop('on', self.d), amount, kw.pop('bank', self.bank),
                                    kw.pop('method', 'cash'), **kw)


class IssueTests(BillBase):
    def test_numbers_are_sequential_per_year(self):
        self.assertEqual([self.bill().number, self.bill().number], [1, 2])

    def test_amount_must_be_positive_whole_rials(self):
        for bad in (0, -5, '1.5', 'x', None):
            with self.assertRaises(Invalid, msg=repr(bad)):
                self.bill(bad)

    def test_income_account_must_be_a_postable_resource(self):
        with self.assertRaises(Invalid):
            bills.issue_bill(self.dehyar, self.year, self.d, self.party, self.salary, 10, 'x')
        self.tax.is_postable = False
        self.tax.save()
        with self.assertRaises(Invalid):
            self.bill()

    def test_date_inside_year_and_year_open(self):
        with self.assertRaises(Invalid):
            self.bill(on=date(2030, 1, 1))
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.bill()

    def test_foreign_party_refused(self):
        other = make_user('dehyari')
        om = make_municipality(other, village='روستای دیگر')
        foreign = Party.objects.create(municipality=om, name='غریبه')
        with self.assertRaises(Invalid):
            bills.issue_bill(self.dehyar, self.year, self.d, foreign, self.tax, 10, 'x')

    def test_citizen_forbidden_other_tenant_notfound(self):
        with self.assertRaises(Forbidden):
            bills.issue_bill(make_user('citizen'), self.year, self.d, self.party, self.tax, 10, 'x')
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        with self.assertRaises(NotFound):
            bills.issue_bill(other, self.year, self.d, self.party, self.tax, 10, 'x')
        with self.assertRaises(NotFound):
            bills.get_bill(other, self.bill().id)

    def test_db_rejects_zero_amount(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bill.objects.create(municipality=self.muni, fiscal_year=self.year, number=9, date=self.d,
                                party=self.party, income_account=self.tax, description='x', amount=0)


class PaymentTests(BillBase):
    def test_payment_posts_balanced_temporary_income_voucher(self):
        b = self.bill(1000)
        p = self.pay(b, 400)
        v = p.voucher
        self.assertEqual((v.kind, v.status), ('income', 'temporary'))
        self.assertTrue(ledger.is_balanced(v))
        lines = {ln.account_id: ln for ln in v.lines.all()}
        self.assertEqual(lines[self.bank.id].debit, 400)
        self.assertEqual(lines[self.tax.id].credit, 400)
        self.assertEqual(lines[self.tax.id].party_id, self.party.id)

    def test_status_follows_payments(self):
        b = self.bill(1000)
        self.assertEqual(bills.summary(b)['status'], 'unpaid')
        self.pay(b, 400)
        s = bills.summary(b)
        self.assertEqual((s['status'], s['paid'], s['remaining']), ('partial', 400, 600))
        self.pay(b, 600)
        self.assertEqual(bills.summary(b)['status'], 'paid')

    def test_cannot_overpay(self):
        b = self.bill(1000)
        self.pay(b, 700)
        with self.assertRaises(Conflict):
            self.pay(b, 301)
        self.assertEqual(BillPayment.objects.count(), 1)

    def test_failed_payment_leaves_no_voucher(self):
        b = self.bill(1000)
        before = ledger.vouchers_for(self.dehyar, self.year).count()
        with self.assertRaises(Conflict):
            self.pay(b, 5000)
        self.assertEqual(ledger.vouchers_for(self.dehyar, self.year).count(), before)

    def test_bank_account_must_be_postable_asset(self):
        b = self.bill()
        with self.assertRaises(Invalid):
            self.pay(b, 10, bank=self.tax)

    def test_bad_method_and_amount(self):
        b = self.bill()
        with self.assertRaises(Invalid):
            self.pay(b, 10, method='gold')
        for bad in (0, -1, '2.5'):
            with self.assertRaises(Invalid, msg=repr(bad)):
                self.pay(b, bad)

    def test_canceled_bill_takes_no_payment(self):
        b = self.bill()
        bills.cancel_bill(self.dehyar, b)
        with self.assertRaises(Conflict):
            self.pay(b, 10)

    def test_cancel_refused_once_paid(self):
        b = self.bill()
        self.pay(b, 10)
        with self.assertRaises(Conflict):
            bills.cancel_bill(self.dehyar, b)

    def test_closed_year_blocks_payment(self):
        b = self.bill()
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.pay(b, 10)

    def test_other_tenant_cannot_pay(self):
        b = self.bill()
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        with self.assertRaises(NotFound):
            bills.record_payment(other, b, self.d, 10, self.bank, 'cash')

    def test_payment_feeds_budget_actual(self):
        from main.accounting import budget
        budget.set_budget(self.dehyar, self.year, self.tax, 2000)
        self.pay(self.bill(1000), 1000)
        row = next(r for r in budget.report(self.dehyar, self.year)[0] if r['account_id'] == self.tax.id)
        self.assertEqual(row['actual'], 1000)


class BillViewTests(BillBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_issue_and_pay_through_pages(self):
        url = reverse('main:acc_bills', args=[self.year.id])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {'date': '1404/02/11', 'party': self.party.id, 'income_account': self.tax.id,
                                   'amount': '۱٬۰۰۰', 'description': 'عوارض'})
        bill = Bill.objects.get()
        self.assertRedirects(r, reverse('main:acc_bill_detail', args=[bill.id]), fetch_redirect_response=False)
        pay_url = reverse('main:acc_bill_pay', args=[bill.id])
        r = self.client.post(pay_url, {'date': '1404/02/12', 'amount': '400', 'bank_account': self.bank.id,
                                       'method': 'card', 'reference': '123'})
        self.assertRedirects(r, reverse('main:acc_bill_detail', args=[bill.id]), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('main:acc_bill_detail', args=[bill.id])).status_code, 200)
        self.assertEqual(BillPayment.objects.get().amount, Decimal(400))

    def test_overpay_is_409_and_bad_amount_400(self):
        bill = self.bill(100)
        pay_url = reverse('main:acc_bill_pay', args=[bill.id])
        data = {'date': '1404/02/12', 'amount': '500', 'bank_account': self.bank.id, 'method': 'cash'}
        self.assertEqual(self.client.post(pay_url, data).status_code, 409)
        self.assertEqual(self.client.post(pay_url, {**data, 'amount': '1.5'}).status_code, 400)
        self.assertFalse(BillPayment.objects.exists())

    def test_access(self):
        bill = self.bill()
        urls = [reverse('main:acc_bills', args=[self.year.id]), reverse('main:acc_bill_detail', args=[bill.id])]
        for u in urls:
            self.assertEqual(client_for(make_user('citizen')).get(u).status_code, 302)
            self.assertEqual(client_for().get(u).status_code, 302)
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        for u in urls:
            self.assertEqual(c.get(u).status_code, 404)
        self.assertEqual(c.post(reverse('main:acc_bill_pay', args=[bill.id]), {'amount': '1'}).status_code, 404)
        self.assertEqual(c.post(reverse('main:acc_bill_cancel', args=[bill.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('main:acc_bill_cancel', args=[bill.id])).status_code, 405)


class PaymentVoucherLockTests(BillBase):
    def test_payment_voucher_cannot_be_edited_or_deleted(self):
        b = self.bill(500)
        v = self.pay(b, 500).voucher
        for call in (
            lambda: ledger.update_voucher(self.dehyar, v, description='x', lines=[
                {'account': self.bank, 'debit': 1, 'credit': 0}, {'account': self.tax, 'debit': 0, 'credit': 1}]),
            lambda: ledger.delete_voucher(self.dehyar, v),
            lambda: ledger.check_editable(self.dehyar, v),
        ):
            with self.assertRaises(Conflict):
                call()
        self.assertEqual(bills.summary(b)['paid'], 500)

    def test_payment_voucher_can_still_be_finalized(self):
        v = self.pay(self.bill(500), 500).voucher
        self.assertEqual(ledger.finalize(self.dehyar, v).status, 'final')

    def test_cancel_payment_removes_payment_and_voucher(self):
        b = self.bill(500)
        p = self.pay(b, 500)
        bills.cancel_payment(self.dehyar, p)
        self.assertEqual(bills.summary(b)['status'], 'unpaid')
        p.voucher.refresh_from_db()
        self.assertIsNotNone(p.voucher.deleted_at)
        self.assertFalse(BillPayment.objects.exists())
        self.pay(b, 500)  # the amount is payable again

    def test_cancel_refused_for_final_voucher_until_reverted(self):
        p = self.pay(self.bill(500), 500)
        ledger.finalize(self.dehyar, p.voucher)
        with self.assertRaises(Conflict):
            bills.cancel_payment(self.dehyar, p)
        self.assertTrue(BillPayment.objects.exists())

    def test_cancel_refused_in_closed_year_and_for_other_tenant(self):
        p = self.pay(self.bill(500), 500)
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        with self.assertRaises(NotFound):
            bills.cancel_payment(other, p)
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            bills.cancel_payment(self.dehyar, p)

    def test_cancel_payment_page(self):
        client = client_for(self.dehyar)
        p = self.pay(self.bill(500), 500)
        url = reverse('main:acc_payment_cancel', args=[p.id])
        self.assertEqual(client.get(url).status_code, 405)
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        self.assertEqual(client_for(other).post(url).status_code, 404)
        self.assertRedirects(client.post(url), reverse('main:acc_bill_detail', args=[p.bill_id]),
                             fetch_redirect_response=False)
        self.assertFalse(BillPayment.objects.exists())
