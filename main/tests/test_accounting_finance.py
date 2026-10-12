"""Credit provisioning, contracts and statements, guarantees, payable-document treasury, status change, images."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from main.accounting import budget, contracts, credit, images, ledger, treasury
from main.models import Account, CostCenter, DocumentImage, Party
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.test_accounting_ledger import LedgerBase, line, make_user
from main.tests.helpers import make_municipality


class FinanceBase(LedgerBase):
    def setUp(self):
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='پیمانکار نمونه')
        self.later = date(2025, 9, 1)


class CreditTests(FinanceBase):
    def prov(self, amount, **kw):
        return credit.create_provision(self.dehyar, self.year, self.d, [
            {'use_account': self.salary, 'source_account': self.tax, 'amount': amount}], **kw)

    def test_within_budget_and_numbered(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        a, b = self.prov(400), self.prov(600)
        self.assertEqual((a.number, b.number), (1, 2))

    def test_cannot_exceed_budget_across_provisions(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        self.prov(700)
        with self.assertRaises(Conflict):
            self.prov(301)
        self.assertEqual(credit.provisioned(self.year, self.salary), 700)

    def test_no_budget_means_nothing_to_provision(self):
        with self.assertRaises(Conflict):
            self.prov(1)

    def test_cancelled_provision_frees_the_amount(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        p = self.prov(1000)
        credit.cancel_provision(self.dehyar, p)
        self.prov(1000)

    def test_same_account_twice_in_one_provision_is_summed(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        row = {'use_account': self.salary, 'source_account': self.tax, 'amount': 600}
        with self.assertRaises(Conflict):
            credit.create_provision(self.dehyar, self.year, self.d, [row, dict(row)])

    def test_account_kinds_and_amounts(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        bad = [
            {'use_account': self.bank, 'source_account': self.tax, 'amount': 5},
            {'use_account': self.salary, 'source_account': self.salary, 'amount': 5},
            {'use_account': self.salary, 'source_account': self.tax, 'amount': 0},
            {'use_account': self.salary, 'source_account': self.tax, 'amount': -5},
        ]
        for row in bad:
            with self.assertRaises(Invalid):
                credit.create_provision(self.dehyar, self.year, self.d, [row])
        with self.assertRaises(Invalid):
            credit.create_provision(self.dehyar, self.year, self.d, [])

    def test_dates_checked(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        with self.assertRaises(Invalid):
            self.prov(1, expires_on=self.d - timedelta(days=1))
        with self.assertRaises(Invalid):
            credit.create_provision(self.dehyar, self.year, date(2020, 1, 1), [
                {'use_account': self.salary, 'source_account': self.tax, 'amount': 1}])

    def test_foreign_municipality_and_citizen(self):
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        with self.assertRaises(NotFound):
            credit.create_provision(other, self.year, self.d, [])
        with self.assertRaises(Forbidden):
            credit.create_provision(make_user('citizen'), self.year, self.d, [])

    def test_availability_report(self):
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        self.prov(250)
        row = credit.availability(self.dehyar, self.year)[0]
        self.assertEqual((row['budget'], row['reserved'], row['free']), (1000, 250, 750))


class ContractTests(FinanceBase):
    def make(self, **kw):
        data = dict(subject='آسفالت کوچه', contractor=self.party, date=self.d, start_date=self.d,
                    end_date=self.d + timedelta(days=100), amount=1_000_000, vat_pct=10, good_performance_pct=5,
                    contractor_insurance_pct=7, employer_insurance_pct=16, tax_pct=3)
        data.update(kw)
        return contracts.create_contract(self.dehyar, self.year, **data)

    def test_statement_deductions_and_net(self):
        c = self.make()
        s = contracts.add_statement(self.dehyar, c, self.d, 200_000)
        self.assertEqual((s.vat, s.good_performance, s.contractor_insurance, s.employer_insurance, s.tax),
                         (20_000, 10_000, 14_000, 32_000, 6_000))
        self.assertEqual(s.net, 200_000 + 20_000 - 10_000 - 14_000 - 6_000)   # employer insurance is not deducted
        self.assertEqual(s.number, 1)

    def test_rounding_is_half_up_whole_rials(self):
        c = self.make(vat_pct=Decimal('9.5'), good_performance_pct=0, contractor_insurance_pct=0, tax_pct=0)
        s = contracts.add_statement(self.dehyar, c, self.d, 1005)
        self.assertEqual(s.vat, 95)   # 1005 * 9.5% = 95.475 -> 95

    def test_cannot_exceed_ceiling(self):
        c = self.make(ceiling=1_200_000)
        contracts.add_statement(self.dehyar, c, self.d, 1_000_000)
        with self.assertRaises(Conflict):
            contracts.add_statement(self.dehyar, c, self.d, 200_001)
        contracts.add_statement(self.dehyar, c, self.d, 200_000)

    def test_cancelled_statement_frees_the_ceiling(self):
        c = self.make()
        s = contracts.add_statement(self.dehyar, c, self.d, 1_000_000)
        contracts.cancel_statement(self.dehyar, s)
        contracts.add_statement(self.dehyar, c, self.d, 1_000_000)

    def test_only_active_contracts_take_statements(self):
        c = self.make()
        contracts.set_status(self.dehyar, c, 'suspended')
        with self.assertRaises(Conflict):
            contracts.add_statement(self.dehyar, c, self.d, 10)
        contracts.set_status(self.dehyar, c, 'active')
        contracts.set_status(self.dehyar, c, 'terminated')
        with self.assertRaises(Conflict):
            contracts.set_status(self.dehyar, c, 'active')

    def test_statement_date_inside_contract_period(self):
        c = self.make()
        with self.assertRaises(Invalid):
            contracts.add_statement(self.dehyar, c, self.d + timedelta(days=200), 10)

    def test_validation(self):
        for kw in ({'amount': 0}, {'amount': -5}, {'ceiling': 10}, {'vat_pct': 101}, {'tax_pct': -1},
                   {'end_date': self.d - timedelta(days=1)}, {'subject': ' '}, {'vat_pct': 'x'}):
            with self.assertRaises(Invalid, msg=str(kw)):
                self.make(**kw)

    def test_ceiling_defaults_to_amount_and_numbers_sequential(self):
        a, b = self.make(), self.make()
        self.assertEqual((a.ceiling, a.number, b.number), (1_000_000, 1, 2))

    def test_foreign_party_or_cost_center_refused(self):
        other = make_user('dehyari')
        other_muni = make_municipality(other, village='دیگر')
        foreign = Party.objects.create(municipality=other_muni, name='x')
        with self.assertRaises(Invalid):
            self.make(contractor=foreign)
        cc = CostCenter.objects.create(municipality=other_muni, code='1', title='x')
        with self.assertRaises(Invalid):
            self.make(cost_center=cc)

    def test_other_tenant_cannot_use_contract(self):
        c = self.make()
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        with self.assertRaises(NotFound):
            contracts.add_statement(other, c, self.d, 10)
        with self.assertRaises(NotFound):
            contracts.get_contract(other, c.pk)


class GuaranteeTests(FinanceBase):
    def make(self, **kw):
        data = dict(party=self.party, kind='good_performance', doc_kind='cheque', serial='123', date=self.d,
                    expires_on=self.d + timedelta(days=90), amount=500)
        data.update(kw)
        return contracts.create_guarantee(self.dehyar, **data)

    def test_expiry_states(self):
        g = self.make()
        self.assertEqual(contracts.expiry_state(g, self.d), 'ok')
        self.assertEqual(contracts.expiry_state(g, self.d + timedelta(days=70)), 'soon')
        self.assertEqual(contracts.expiry_state(g, self.d + timedelta(days=91)), 'expired')
        contracts.set_guarantee_status(self.dehyar, g, 'returned', self.d)
        g.refresh_from_db()
        self.assertEqual(contracts.expiry_state(g, self.d + timedelta(days=91)), 'ok')

    def test_status_changes_once(self):
        g = self.make()
        contracts.set_guarantee_status(self.dehyar, g, 'seized', self.d)
        with self.assertRaises(Conflict):
            contracts.set_guarantee_status(self.dehyar, g, 'returned', self.d)
        with self.assertRaises(Invalid):
            contracts.set_guarantee_status(self.dehyar, self.make(serial='9'), 'active', self.d)

    def test_validation_and_duplicates(self):
        self.make()
        with self.assertRaises(Conflict):
            self.make()
        self.make(doc_kind='promissory')   # same serial, other document kind is fine
        for kw in ({'amount': 0}, {'kind': 'x'}, {'doc_kind': 'x'}, {'serial': ''},
                   {'expires_on': self.d - timedelta(days=1)}):
            with self.assertRaises(Invalid, msg=str(kw)):
                self.make(**{'serial': '77', **kw})


class TreasuryTests(FinanceBase):
    def issue(self, **kw):
        data = dict(kind='cheque', serial='C1', party=self.party, bank_account=self.bank, issue_date=self.d,
                    due_date=self.d + timedelta(days=30), amount=1000)
        data.update(kw)
        return treasury.issue(self.dehyar, self.year, **data)

    def test_lifecycle_and_history(self):
        doc = self.issue()
        treasury.change_status(self.dehyar, doc, 'returned', self.later)
        treasury.change_status(self.dehyar, doc, 'issued', self.later)
        treasury.change_status(self.dehyar, doc, 'passed', self.later)
        self.assertEqual([e.status for e in doc.events.all()], ['issued', 'returned', 'issued', 'passed'])
        with self.assertRaises(Conflict):
            treasury.change_status(self.dehyar, doc, 'canceled', self.later)

    def test_validation(self):
        self.issue()
        with self.assertRaises(Conflict):
            self.issue()
        for kw in ({'amount': 0}, {'due_date': self.d - timedelta(days=1)}, {'bank_account': self.tax},
                   {'kind': 'x'}, {'issue_date': date(2020, 1, 1)}, {'serial': ' '}):
            with self.assertRaises(Invalid, msg=str(kw)):
                self.issue(**{'serial': 'Z', **kw})

    def test_closed_year(self):
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.issue()

    def test_status_date_before_issue_refused(self):
        doc = self.issue()
        with self.assertRaises(Invalid):
            treasury.change_status(self.dehyar, doc, 'passed', self.d - timedelta(days=1))

    def test_other_tenant(self):
        doc = self.issue()
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        with self.assertRaises(NotFound):
            treasury.change_status(other, doc, 'passed', self.later)


class StatusChangeTests(FinanceBase):
    def test_bulk_finalize_skips_unbalanced_and_revert_needs_mayor(self):
        for _ in range(3):
            self.voucher()
        ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [line(self.bank, debit=5)])  # no. 4
        changed, skipped = ledger.change_status_range(self.dehyar, self.year, 1, 4, 'final')
        self.assertEqual(changed, 3)
        self.assertEqual([n for n, _ in skipped], [4])
        changed, _ = ledger.change_status_range(self.dehyar, self.year, 1, 2, 'temporary')
        self.assertEqual(changed, 2)

    def test_bad_ranges(self):
        for lo, hi in ((0, 5), (5, 1), (None, 3), (1, 99999)):
            with self.assertRaises(Invalid):
                ledger.change_status_range(self.dehyar, self.year, lo, hi, 'final')
        with self.assertRaises(Invalid):
            ledger.change_status_range(self.dehyar, self.year, 1, 2, 'x')



class ImageTests(FinanceBase):
    PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
           b'\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82')

    def test_upload_rules(self):
        import tempfile
        with override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp()):
            v = self.voucher()
            img = images.upload(self.dehyar, v, SimpleUploadedFile('a.png', self.PNG, 'image/png'), 'فاکتور')
            self.assertEqual(DocumentImage.objects.get().voucher, v)
            for name, data in (('a.exe', b'MZ'), ('a.png', b'x' * (5 * 1024 * 1024 + 1)), ('a.png', b'not a png')):
                with self.assertRaises(Invalid, msg=name):
                    images.upload(self.dehyar, v, SimpleUploadedFile(name, data), 't')
            with self.assertRaises(Invalid):
                images.upload(self.dehyar, v, None, 't')
            ledger.finalize(self.dehyar, v)
            with self.assertRaises(Invalid):
                images.delete(self.dehyar, img)

    def test_other_tenant_cannot_read_or_upload(self):
        import tempfile
        with override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp()):
            v = self.voucher()
            img = images.upload(self.dehyar, v, SimpleUploadedFile('a.png', self.PNG, 'image/png'), 't')
            other = make_user('dehyari')
            make_municipality(other, village='دیگر')
            with self.assertRaises(NotFound):
                images.get_image(other, img.pk)
            with self.assertRaises(NotFound):
                images.upload(other, v, SimpleUploadedFile('a.png', self.PNG), 't')
