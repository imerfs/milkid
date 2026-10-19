"""The date lock reaches every dated accounting document: instalments, contracts, payables, transport income, credit provisions,
payroll months."""
from datetime import date, timedelta

from main.accounting import budget, contracts, controls, credit, instalments, payroll, transport, treasury
from main.models import Party
from main.office.errors import Conflict
from main.tests.test_accounting_ledger import LedgerBase
from main.tests.test_accounting_payroll import NID


class LockedDocuments(LedgerBase):
    """The lock is set after the documents exist; touching anything dated inside it must then fail."""

    def setUp(self):
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='علی رضایی')
        self.inside = date(2025, 5, 1)                       # 1404/02/11, before the lock
        self.after = date(2025, 9, 1)

    def lock(self):
        controls.set_lock(self.dehyar, date(2025, 6, 30))

    def test_instalment_plans_payments_and_cheques(self):
        plan = instalments.create_plan(self.dehyar, self.year, party=self.party, total_debt=1_000_000, cash_paid=0, count=2,
                                       first_due=date(2025, 6, 1), on=self.inside)
        first = plan.installments.first()
        self.lock()
        with self.assertRaises(Conflict):
            instalments.create_plan(self.dehyar, self.year, party=self.party, total_debt=1_000, cash_paid=0, count=1,
                                    first_due=date(2025, 6, 1), on=self.inside)
        with self.assertRaises(Conflict):
            instalments.pay(self.dehyar, first, self.inside, 100, 'cash')
        with self.assertRaises(Conflict):
            instalments.cancel_plan(self.dehyar, plan, self.after)             # the plan itself is dated inside the lock
        with self.assertRaises(Conflict):
            instalments.add_person(self.dehyar, plan, self.party, 'guarantor')
        instalments.pay(self.dehyar, first, self.after, 100, 'cash')            # a payment after the lock is fine

    def test_contracts_statements_and_guarantees(self):
        contract = contracts.create_contract(self.dehyar, self.year, subject='آسفالت', contractor=self.party, date=self.inside,
                                             start_date=self.inside, end_date=self.inside + timedelta(days=200), amount=1_000_000,
                                             vat_pct=10, good_performance_pct=5, contractor_insurance_pct=7,
                                             employer_insurance_pct=16, tax_pct=3)
        statement = contracts.add_statement(self.dehyar, contract, self.after, 100_000)
        self.lock()
        with self.assertRaises(Conflict):
            contracts.add_statement(self.dehyar, contract, self.inside, 1000)
        with self.assertRaises(Conflict):
            contracts.set_status(self.dehyar, contract, 'finished')              # the contract is dated inside the lock
        with self.assertRaises(Conflict):
            contracts.create_contract(self.dehyar, self.year, subject='دیگر', contractor=self.party, date=self.inside,
                                      start_date=self.inside, end_date=self.inside + timedelta(days=10), amount=1000)
        with self.assertRaises(Conflict):
            contracts.create_guarantee(self.dehyar, party=self.party, kind='good_performance', doc_kind='cheque', serial='1',
                                       date=self.inside, expires_on=self.after, amount=100)
        contracts.cancel_statement(self.dehyar, statement)                       # dated after the lock: allowed

    def test_payable_documents(self):
        doc = treasury.issue(self.dehyar, self.year, kind='cheque', serial='11', party=self.party, bank_account=self.bank,
                             issue_date=self.inside, due_date=self.after, amount=1000)
        self.lock()
        with self.assertRaises(Conflict):
            treasury.issue(self.dehyar, self.year, kind='cheque', serial='12', party=self.party, bank_account=self.bank,
                           issue_date=self.inside, due_date=self.after, amount=1000)
        with self.assertRaises(Conflict):
            treasury.change_status(self.dehyar, doc, 'passed', self.inside)
        treasury.change_status(self.dehyar, doc, 'passed', self.after)

    def test_transport_income_and_credit_provisions(self):
        income = transport.record(self.dehyar, self.year, on=self.inside, plate='11ب111', service='عوارض', amount=500)
        budget.set_budget(self.dehyar, self.year, self.salary, 1000)
        provision = credit.create_provision(self.dehyar, self.year, self.inside, [
            {'use_account': self.salary, 'source_account': self.tax, 'amount': 100}])
        self.lock()
        with self.assertRaises(Conflict):
            transport.record(self.dehyar, self.year, on=self.inside, plate='22ب222', service='عوارض', amount=500)
        with self.assertRaises(Conflict):
            transport.cancel(self.dehyar, income)
        with self.assertRaises(Conflict):
            credit.create_provision(self.dehyar, self.year, self.inside, [
                {'use_account': self.salary, 'source_account': self.tax, 'amount': 100}])
        with self.assertRaises(Conflict):
            credit.cancel_provision(self.dehyar, provision)

    def test_payroll_months_are_locked_when_their_last_day_is_inside_the_lock(self):
        employee = payroll.add_employee(self.dehyar, first_name='علی', last_name='رضایی', national_id=NID[0],
                                        calc_group='official_worker', list_title='کارگران رسمی', job_title='کارگر',
                                        start_date=date(2024, 1, 1))
        payroll.set_allowances(self.dehyar, employee, {1: 30_000_000})
        run = payroll.run_payroll(self.dehyar, 1404, 3)                          # khordad ends 1404/03/31 = 2025-06-21
        self.lock()                                                              # lock until 2025-06-30
        with self.assertRaises(Conflict):
            payroll.run_payroll(self.dehyar, 1404, 3)
        with self.assertRaises(Conflict):
            payroll.finalize_run(self.dehyar, run)
        with self.assertRaises(Conflict):
            payroll.delete_run(self.dehyar, run)
        with self.assertRaises(Conflict):
            payroll.set_attendance(self.dehyar, employee, 1404, 3, worked_days=30)
        with self.assertRaises(Conflict):
            payroll.set_misc(self.dehyar, employee, 1404, 3, advance=10)
        with self.assertRaises(Conflict):
            payroll.add_mission(self.dehyar, employee, order_no='1', order_date=date(2025, 6, 1), start_date=date(2025, 6, 2),
                                end_date=date(2025, 6, 3), origin='الف', destination='ب')
        self.assertTrue(payroll.run_payroll(self.dehyar, 1404, 4))               # tir ends 1404/04/31 = 2025-07-22: open

    def test_lifting_the_lock_reopens_everything(self):
        self.lock()
        controls.set_lock(self.dehyar, None)
        self.assertTrue(transport.record(self.dehyar, self.year, on=self.inside, plate='11ب111', service='عوارض', amount=500))
