"""Workspace pages of credit provisioning, contracts, guarantees, treasury, images and status change (HTTP level)."""
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from main.accounting import budget, contracts, credit, treasury
from main.models import Account, Contract, CreditProvision, DocumentImage, Guarantee, PayableDocument, Voucher
from main.tests.helpers import client_for, make_municipality
from main.tests.test_accounting_finance import ImageTests
from main.tests.test_accounting_panel import PanelBase, make_user, trigger


class FinancePanelBase(PanelBase):
    def setUp(self):
        super().setUp()
        self.salary = Account.objects.get(municipality=self.muni, code='6010101001')

    def post(self, name, *args, client=None, **data):
        return (client or self.client).post(reverse(f'main:{name}', args=args), data)

    def get(self, name, *args, client=None, **params):
        return (client or self.client).get(reverse(f'main:{name}', args=args), params)


class TabTests(FinancePanelBase):
    def test_every_new_tab_renders_with_its_title(self):
        for tab, title in (('credit', 'تامین اعتبار'), ('contracts', 'قراردادها'), ('guarantees', 'ضمانت‌نامه‌ها'),
                           ('payables', 'خزانه اسناد پرداختی'), ('images', 'تصاویر اسناد'),
                           ('statuschange', 'تغییر وضعیت اسناد')):
            r = self.get('acc_panel', tab=tab)
            self.assertEqual(r.status_code, 200, tab)
            self.assertContains(r, title)

    def test_nothing_for_citizens(self):
        citizen = client_for(make_user('citizen'))
        for name, args in (('acc_panel', ()), ('acc_p_credit_new', (self.year.id,)), ('acc_p_guarantee_new', ()),
                           ('acc_p_status_change', (self.year.id,))):
            r = citizen.post(reverse(f'main:{name}', args=args))
            self.assertIn(r.status_code, (302, 403), name)


class CreditViewTests(FinancePanelBase):
    def test_provision_saved_and_budget_enforced(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        row = {'date': '۱۴۰۴/۰۲/۱۱', 'use_account': [self.salary.id, ''], 'source_account': [self.tax.id, ''],
               'project': ['پروژه', ''], 'description': ['', ''], 'amount': ['۸۰۰', '']}
        r = self.post('acc_p_credit_new', self.year.id, **row)
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        self.assertEqual(CreditProvision.objects.get().lines.get().amount, 800)
        row['amount'] = ['300', '']
        r = self.post('acc_p_credit_new', self.year.id, **row)
        self.assertEqual(r.status_code, 409)
        self.assertContains(r, 'کافی نیست', status_code=409)

    def test_other_tenant_cannot_open_or_cancel(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        prov = credit.create_provision(self.dehyar, self.year, self.d, [
            {'use_account': self.salary, 'source_account': self.tax, 'amount': 5}])
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        c = client_for(other)
        self.assertEqual(self.get('acc_p_credit_detail', prov.id, client=c).status_code, 404)
        self.assertEqual(self.post('acc_p_credit_cancel', prov.id, client=c).status_code, 404)


class ContractViewTests(FinancePanelBase):
    def contract_data(self, **extra):
        data = {'subject': 'آسفالت', 'contractor': self.party.id, 'date': '۱۴۰۴/۰۲/۱۱', 'start_date': '۱۴۰۴/۰۲/۱۱',
                'end_date': '۱۴۰۴/۱۲/۱۱', 'amount': '۱,۰۰۰,۰۰۰', 'vat_pct': '10', 'tax_pct': '3'}
        data.update(extra)
        return data

    def test_create_and_statement_flow(self):
        r = self.post('acc_p_contract_new', self.year.id, **self.contract_data())
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        c = Contract.objects.get()
        r = self.post('acc_p_statement_new', c.id, date='۱۴۰۴/۰۳/۰۱', gross='۱۰۰۰۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        s = c.statements.get()
        self.assertEqual((s.vat, s.tax, s.net), (10000, 3000, 107000))
        r = self.post('acc_p_statement_new', c.id, date='۱۴۰۴/۰۳/۰۱', gross='۹۰۰۰۰۱')
        self.assertEqual(r.status_code, 409)
        self.assertContains(self.get('acc_p_contract_detail', c.id), 'صورت‌وضعیت')

    def test_bad_form_shows_error_and_creates_nothing(self):
        r = self.post('acc_p_contract_new', self.year.id, **self.contract_data(amount='0'))
        self.assertEqual(r.status_code, 400)
        r = self.post('acc_p_contract_new', self.year.id, **self.contract_data(contractor='99999'))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Contract.objects.exists())

    def test_foreign_statement_cancel_is_404(self):
        c = contracts.create_contract(self.dehyar, self.year, subject='x', contractor=self.party, date=self.d,
                                      start_date=self.d, end_date=self.d + timedelta(days=9), amount=100)
        s = contracts.add_statement(self.dehyar, c, self.d, 10)
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        self.assertEqual(self.post('acc_p_statement_cancel', s.id, client=client_for(other)).status_code, 404)


class GuaranteeAndTreasuryViewTests(FinancePanelBase):
    def test_guarantee_create_and_return(self):
        r = self.post('acc_p_guarantee_new', kind='bid', doc_kind='cheque', party=self.party.id, serial='55',
                      date='۱۴۰۴/۰۲/۱۱', expires_on='۱۴۰۴/۰۵/۱۱', amount='۵۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        g = Guarantee.objects.get()
        self.assertEqual(self.post('acc_p_guarantee_action', g.id, 'returned').status_code, 204)
        self.assertEqual(self.post('acc_p_guarantee_action', g.id, 'seized').status_code, 409)
        self.assertEqual(self.post('acc_p_guarantee_action', g.id, 'bogus').status_code, 404)

    def test_payable_status_flow(self):
        r = self.post('acc_p_payable_new', self.year.id, kind='cheque', serial='A1', party=self.party.id,
                      bank_account=self.bank.id, issue_date='۱۴۰۴/۰۲/۱۱', due_date='۱۴۰۴/۰۳/۱۱', amount='۱۰۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        doc = PayableDocument.objects.get()
        r = self.post('acc_p_payable_status', doc.id, status='passed', date='۱۴۰۴/۰۳/۱۲')
        self.assertEqual(r.status_code, 204)
        r = self.post('acc_p_payable_status', doc.id, status='returned', date='۱۴۰۴/۰۳/۱۳')
        self.assertEqual(r.status_code, 409)
        self.assertContains(r, 'مجاز نیست', status_code=409)


class StatusChangeViewTests(FinancePanelBase):
    def test_range_finalizes_and_reports(self):
        self.voucher(), self.voucher()
        r = self.post('acc_p_status_change', self.year.id, number_from='1', number_to='2', target='final')
        self.assertEqual(r.status_code, 204)
        self.assertIn('2', trigger(r)['accDone']['message'])
        self.assertEqual(Voucher.objects.filter(status='final').count(), 2)
        r = self.post('acc_p_status_change', self.year.id, number_from='2', number_to='1', target='final')
        self.assertEqual(r.status_code, 400)


class ImageViewTests(FinancePanelBase):
    def test_upload_download_and_isolation(self):
        with override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp()):
            v = self.voucher()
            png = SimpleUploadedFile('a.png', ImageTests.PNG, 'image/png')
            r = self.post('acc_p_image_new', self.year.id, number=str(v.number), title='فاکتور', file=png)
            self.assertEqual(r.status_code, 204, r.content.decode()[:300])
            img = DocumentImage.objects.get()
            r = self.get('acc_p_image_file', img.id)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
            other = make_user('dehyari')
            make_municipality(other, village='دیگر')
            self.assertEqual(self.get('acc_p_image_file', img.id, client=client_for(other)).status_code, 404)
            r = self.post('acc_p_image_new', self.year.id, number='999', title='x',
                          file=SimpleUploadedFile('a.png', ImageTests.PNG))
            self.assertEqual(r.status_code, 400)
