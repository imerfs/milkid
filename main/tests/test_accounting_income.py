"""Instalment plans (schedule, payments, cheque treasury) and transport income."""
import tempfile
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings

from main.accounting import images, instalments, transport
from main.models import Installment, Party
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.helpers import make_municipality
from main.tests.test_accounting_finance import ImageTests
from main.tests.test_accounting_ledger import LedgerBase, make_user


class IncomeBase(LedgerBase):
    def setUp(self):
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='علی رضایی')
        self.first = date(2025, 6, 1)   # 1404/03/11

    def plan(self, **kw):
        data = dict(party=self.party, total_debt=1_000_000, cash_paid=100_000, count=4, first_due=self.first,
                    on=self.d)
        data.update(kw)
        return instalments.create_plan(self.dehyar, self.year, **data)

    def other_actor(self):
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        return other


class ScheduleTests(IncomeBase):
    def test_plan_amount_and_schedule_sum_exactly(self):
        plan = self.plan(total_debt=1_000_001, cash_paid=0, count=3)
        amounts = [i.amount for i in plan.installments.all()]
        self.assertEqual(sum(amounts), 1_000_001)
        self.assertEqual(amounts, [333_333, 333_333, 333_335])
        self.assertEqual(plan.plan_amount, 1_000_001)

    def test_cash_is_deducted_and_numbers_sequential(self):
        a, b = self.plan(), self.plan()
        self.assertEqual((a.plan_amount, a.number, b.number), (900_000, 1, 2))

    def test_due_dates_are_jalali_months_apart_and_clamped(self):
        # 1404/06/31 -> 1404/07/30 (Mehr has 30 days) -> 1404/08/30
        plan = self.plan(first_due=date(2025, 9, 22), count=3, on=self.d)
        import jdatetime
        days = [jdatetime.date.fromgregorian(date=i.due_date).strftime('%Y/%m/%d') for i in plan.installments.all()]
        self.assertEqual(days, ['1404/06/31', '1404/07/30', '1404/08/30'])

    def test_esfand_clamps_to_29_in_a_common_year(self):
        self.assertEqual(str(instalments.add_jalali_months(date(2025, 1, 20), 1)), '2025-02-19')   # 1403/11/01 -> 1403/12/01
        # 1404/11/30 + 1 month = 1404/12/29 (1404 is not a leap year)
        import jdatetime
        start = jdatetime.date(1404, 11, 30).togregorian()
        self.assertEqual(jdatetime.date.fromgregorian(date=instalments.add_jalali_months(start, 1)).strftime('%Y/%m/%d'),
                         '1404/12/29')

    def test_validation(self):
        bad = ({'total_debt': 0}, {'total_debt': -1}, {'cash_paid': 1_000_000}, {'cash_paid': 2_000_000},
               {'count': 0}, {'count': 61}, {'count': 'x'}, {'first_due': self.d - timedelta(days=1)},
               {'on': date(2020, 1, 1)}, {'total_debt': 3, 'cash_paid': 0, 'count': 4})
        for kw in bad:
            with self.assertRaises(Invalid, msg=str(kw)):
                self.plan(**kw)

    def test_closed_year_and_foreign_party(self):
        foreign = Party.objects.create(municipality=make_municipality(make_user('dehyari'), village='x'), name='x')
        with self.assertRaises(Invalid):
            self.plan(party=foreign)
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.plan()

    def test_db_rejects_overpaid_instalment(self):
        inst = self.plan().installments.first()
        inst.paid_amount = inst.amount + 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            inst.save()


class PaymentTests(IncomeBase):
    def test_cash_payments_partial_then_settled(self):
        plan = self.plan(count=1, total_debt=1000, cash_paid=0)
        inst = plan.installments.get()
        instalments.pay(self.dehyar, inst, self.d, 400, 'cash')
        inst.refresh_from_db()
        self.assertEqual(inst.remaining, 600)
        with self.assertRaises(Conflict):
            instalments.pay(self.dehyar, inst, self.d, 601, 'cash')
        instalments.pay(self.dehyar, inst, self.d, 600, 'transfer')
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'settled')
        self.assertEqual(instalments.counters(plan)['settled'], 1)

    def test_cheque_must_cover_whole_instalment_and_waits_for_treasury(self):
        plan = self.plan(count=2, total_debt=1000, cash_paid=0)
        inst = plan.installments.first()
        with self.assertRaises(Invalid):
            instalments.pay(self.dehyar, inst, self.d, 100, 'cheque', serial='1', cheque_date=self.first)
        with self.assertRaises(Invalid):   # serial and cheque date are required
            instalments.pay(self.dehyar, inst, self.d, 500, 'cheque', serial='', cheque_date=self.first)
        with self.assertRaises(Invalid):
            instalments.pay(self.dehyar, inst, self.d, 500, 'cheque', serial='1')
        instalments.pay(self.dehyar, inst, self.d, 500, 'cheque', serial='1', series='9', cheque_date=self.first,
                        owner_name='علی')
        inst.refresh_from_db()
        self.assertEqual((inst.paid_amount, inst.position), (0, 'office'))
        with self.assertRaises(Conflict):   # cheque already received for this instalment
            instalments.pay(self.dehyar, inst, self.d, 500, 'cash')

    def test_treasury_flow_collect_and_bounce(self):
        plan = self.plan(count=2, total_debt=1000, cash_paid=0)
        a, b = plan.installments.all()
        for inst in (a, b):
            instalments.pay(self.dehyar, inst, self.d, 500, 'cheque', serial=str(inst.seq), cheque_date=self.first)
        with self.assertRaises(Conflict):   # must go through the treasury first
            instalments.move_cheque(self.dehyar, a, 'collected', self.d)
        instalments.move_cheque(self.dehyar, a, 'treasury', self.d)
        instalments.move_cheque(self.dehyar, a, 'collected', self.d)
        a.refresh_from_db()
        self.assertEqual(a.paid_amount, 500)
        with self.assertRaises(Conflict):
            instalments.move_cheque(self.dehyar, a, 'bounced', self.d)
        instalments.move_cheque(self.dehyar, b, 'treasury', self.d)
        instalments.move_cheque(self.dehyar, b, 'bounced', self.d)
        b.refresh_from_db()
        self.assertEqual(b.paid_amount, 0)
        instalments.pay(self.dehyar, b, self.d, 500, 'cash')   # a bounced cheque frees the instalment
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'settled')
        self.assertEqual([e.position for e in a.events.all()], ['office', 'treasury', 'collected'])

    def test_cancel_plan_blocks_payment_and_needs_cheques_cleared(self):
        plan = self.plan(count=2, total_debt=1000, cash_paid=0)
        a = plan.installments.first()
        instalments.pay(self.dehyar, a, self.d, 500, 'cheque', serial='1', cheque_date=self.first)
        with self.assertRaises(Conflict):
            instalments.cancel_plan(self.dehyar, plan, self.d)
        instalments.move_cheque(self.dehyar, a, 'treasury', self.d)
        instalments.move_cheque(self.dehyar, a, 'bounced', self.d)
        instalments.cancel_plan(self.dehyar, plan, self.d)
        with self.assertRaises(Conflict):
            instalments.pay(self.dehyar, a, self.d, 500, 'cash')
        with self.assertRaises(Conflict):
            instalments.cancel_plan(self.dehyar, plan, self.d)

    def test_other_tenant_and_citizen(self):
        inst = self.plan().installments.first()
        with self.assertRaises(NotFound):
            instalments.pay(self.other_actor(), inst, self.d, 10, 'cash')
        with self.assertRaises(Forbidden):
            instalments.pay(make_user('citizen'), inst, self.d, 10, 'cash')
        with self.assertRaises(NotFound):
            instalments.get_installment(self.other_actor(), inst.pk)

    def test_received_documents_filters(self):
        plan = self.plan(count=2, total_debt=1000, cash_paid=0)
        a, b = plan.installments.all()
        instalments.pay(self.dehyar, a, self.d, 500, 'cheque', serial='AAA', cheque_date=self.first, owner_name='حسین')
        instalments.pay(self.dehyar, b, self.d, 500, 'promissory', serial='BBB', cheque_date=self.first)
        instalments.move_cheque(self.dehyar, b, 'treasury', self.d)
        docs = lambda **kw: list(instalments.received_documents(self.dehyar, self.year, **kw))   # noqa: E731
        self.assertEqual(len(docs()), 2)
        self.assertEqual([i.serial for i in docs(position='treasury')], ['BBB'])
        self.assertEqual([i.serial for i in docs(q='حسین')], ['AAA'])
        self.assertEqual(docs(position='bogus').__len__(), 2)

    def test_people_added_once(self):
        plan = self.plan()
        guarantor = Party.objects.create(municipality=self.muni, name='ضامن')
        instalments.add_person(self.dehyar, plan, guarantor, 'guarantor')
        with self.assertRaises(Conflict):
            instalments.add_person(self.dehyar, plan, guarantor, 'guarantor')
        with self.assertRaises(Invalid):
            instalments.add_person(self.dehyar, plan, guarantor, 'bogus')


class PlanImageTests(IncomeBase):
    def test_plan_image_upload_and_isolation(self):
        with override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp()):
            plan = self.plan()
            img = images.upload(self.dehyar, plan, SimpleUploadedFile('a.png', ImageTests.PNG, 'image/png'), 'نامه')
            self.assertEqual((img.plan, img.voucher), (plan, None))
            with self.assertRaises(NotFound):
                images.upload(self.other_actor(), plan, SimpleUploadedFile('a.png', ImageTests.PNG), 'x')
            images.delete(self.dehyar, img)   # plan images are not locked by voucher status
            self.assertEqual(plan.images.count(), 0)


class TransportTests(IncomeBase):
    def rec(self, **kw):
        data = dict(on=self.d, plate='۱۲ ب ۳۴۵ ایران ۶۷', service='ورود ماشین‌آلات', amount=500)
        data.update(kw)
        return transport.record(self.dehyar, self.year, **data)

    def test_numbering_total_and_cancel(self):
        a, b = self.rec(), self.rec(amount=700)
        self.assertEqual((a.number, b.number), (1, 2))
        self.assertEqual(transport.total(self.dehyar, self.year), 1200)
        transport.cancel(self.dehyar, a)
        self.assertEqual(transport.total(self.dehyar, self.year), 700)

    def test_validation(self):
        for kw in ({'amount': 0}, {'amount': -1}, {'plate': ' '}, {'service': ''}, {'on': date(2020, 1, 1)}):
            with self.assertRaises(Invalid, msg=str(kw)):
                self.rec(**kw)
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.rec()

    def test_other_tenant(self):
        income = self.rec()
        with self.assertRaises(NotFound):
            transport.cancel(self.other_actor(), income)
        with self.assertRaises(NotFound):
            transport.incomes_for(self.other_actor(), self.year)
