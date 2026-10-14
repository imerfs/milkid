"""Workspace pages of instalment plans, received cheques, transport income and plan images (HTTP level)."""
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from main.models import DocumentImage, Installment, InstallmentPlan, TransportIncome
from main.tests.helpers import client_for, make_municipality
from main.tests.test_accounting_finance import ImageTests
from main.tests.test_accounting_finance_panel import FinancePanelBase
from main.tests.test_accounting_panel import make_user


class IncomePanelBase(FinancePanelBase):
    PLAN = {'party': '', 'on': '۱۴۰۴/۰۲/۱۱', 'total_debt': '۱٬۲۰۰٬۰۰۰', 'cash_paid': '۲۰۰٬۰۰۰', 'count': '۴',
            'first_due': '۱۴۰۴/۰۳/۱۱'}

    def make_plan(self, **extra):
        r = self.post('acc_p_plan_new', self.year.id, **{**self.PLAN, 'party': self.party.id, **extra})
        self.assertEqual(r.status_code, 204, r.content.decode()[:400])
        return InstallmentPlan.objects.latest('id')


class TabTests(IncomePanelBase):
    def test_tabs_render(self):
        for tab, title in (('plans', 'تقسیط'), ('received', 'خزانه اسناد دریافتی'), ('transport', 'درآمد حمل و نقل'),
                           ('planimages', 'تصاویر پرونده تقسیط')):
            r = self.get('acc_panel', tab=tab)
            self.assertEqual(r.status_code, 200, tab)
            self.assertContains(r, title)

    def test_citizen_refused(self):
        r = client_for(make_user('citizen')).post(self.url('acc_p_plan_new', self.year.id))
        self.assertIn(r.status_code, (302, 403))

    def url(self, name, *args):
        from django.urls import reverse
        return reverse(f'main:{name}', args=args)


class PlanFlowTests(IncomePanelBase):
    def test_create_pay_and_detail(self):
        plan = self.make_plan()
        self.assertEqual((plan.plan_amount, plan.installments.count()), (1_000_000, 4))
        first = plan.installments.first()
        r = self.post('acc_p_installment_pay', first.id, method='cash', on='۱۴۰۴/۰۳/۱۱', amount='۲۵۰۰۰۰')
        self.assertEqual(r.status_code, 200, r.content.decode()[:400])
        self.assertContains(r, 'پرداخت ثبت شد')
        first.refresh_from_db()
        self.assertEqual(first.paid_amount, 250_000)
        r = self.post('acc_p_installment_pay', first.id, method='cash', on='۱۴۰۴/۰۳/۱۱', amount='۱')
        self.assertEqual(r.status_code, 409)
        self.assertContains(self.get('acc_p_plan_detail', plan.id), 'اقساط')
        self.assertContains(self.get('acc_panel', tab='plans'), plan.party.name)

    def test_bad_plan_form(self):
        r = self.post('acc_p_plan_new', self.year.id, **{**self.PLAN, 'party': self.party.id, 'cash_paid': '۱۲۰۰۰۰۰'})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(InstallmentPlan.objects.exists())

    def test_cheque_treasury_over_http(self):
        plan = self.make_plan()
        inst = plan.installments.first()
        r = self.post('acc_p_installment_pay', inst.id, method='cheque', on='۱۴۰۴/۰۳/۰۱', amount='۲۵۰۰۰۰',
                      serial='55', series='9', cheque_date='۱۴۰۴/۰۳/۱۱', owner_name='حسین')
        self.assertEqual(r.status_code, 200, r.content.decode()[:400])
        self.assertContains(self.get('acc_panel', tab='received'), 'حسین')
        self.assertEqual(self.post('acc_p_cheque_move', inst.id, 'collected').status_code, 409)
        self.assertEqual(self.post('acc_p_cheque_move', inst.id, 'treasury').status_code, 204)
        self.assertEqual(self.post('acc_p_cheque_move', inst.id, 'collected').status_code, 204)
        inst.refresh_from_db()
        self.assertEqual(inst.paid_amount, 250_000)
        self.assertContains(self.get('acc_panel', tab='received', position='collected'), '۵۵')
        self.assertContains(self.get('acc_p_cheque_detail', inst.id), 'سابقه')

    def test_cancel_plan(self):
        plan = self.make_plan()
        self.assertEqual(self.post('acc_p_plan_cancel', plan.id).status_code, 204)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'canceled')
        self.assertEqual(self.post('acc_p_plan_cancel', plan.id).status_code, 409)

    def test_person_and_guarantee(self):
        plan = self.make_plan()
        r = self.post('acc_p_plan_person', plan.id, party=self.party.id, relation='guarantor')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.post('acc_p_plan_person', plan.id, party=self.party.id, relation='guarantor').status_code, 409)
        r = self.post('acc_p_plan_guarantee', plan.id, kind='obligations', doc_kind='cheque', party=self.party.id,
                      serial='77', date='۱۴۰۴/۰۲/۱۱', expires_on='۱۴۰۴/۰۸/۱۱', amount='۱۰۰۰')
        self.assertEqual(r.status_code, 200, r.content.decode()[:400])
        self.assertEqual(plan.guarantees.count(), 1)

    def test_other_tenant_gets_404(self):
        plan = self.make_plan()
        inst = plan.installments.first()
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        c = client_for(other)
        self.assertEqual(self.get('acc_p_plan_detail', plan.id, client=c).status_code, 404)
        self.assertEqual(self.post('acc_p_plan_cancel', plan.id, client=c).status_code, 404)
        self.assertEqual(self.post('acc_p_installment_pay', inst.id, client=c, method='cash').status_code, 404)
        self.assertEqual(self.post('acc_p_cheque_move', inst.id, 'treasury', client=c).status_code, 404)
        self.assertEqual(self.post('acc_p_plan_person', plan.id, client=c).status_code, 404)

    def test_plan_image(self):
        with override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp()):
            plan = self.make_plan()
            r = self.post('acc_p_planimage_new', self.year.id, number=str(plan.number), title='نامه',
                          file=SimpleUploadedFile('a.png', ImageTests.PNG, 'image/png'))
            self.assertEqual(r.status_code, 204, r.content.decode()[:300])
            self.assertEqual(DocumentImage.objects.get().plan, plan)
            r = self.post('acc_p_planimage_new', self.year.id, number='99', title='x',
                          file=SimpleUploadedFile('a.png', ImageTests.PNG))
            self.assertEqual(r.status_code, 400)


class TransportViewTests(IncomePanelBase):
    def test_record_and_cancel(self):
        r = self.post('acc_p_transport_new', self.year.id, on='۱۴۰۴/۰۲/۱۱', plate='۱۲ب۳۴۵', service='ورود ماشین‌آلات',
                      amount='۵۰۰٬۰۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        t = TransportIncome.objects.get()
        self.assertContains(self.get('acc_panel', tab='transport'), 'ورود ماشین‌آلات')
        self.assertEqual(self.post('acc_p_transport_new', self.year.id, on='۱۴۰۴/۰۲/۱۱', plate='', service='x',
                                   amount='1').status_code, 400)
        self.assertEqual(self.post('acc_p_transport_cancel', t.id).status_code, 204)
        t.refresh_from_db()
        self.assertEqual(t.status, 'canceled')
