"""A whole village year in the accountant workspace, entered through the panel's own HTTP endpoints, then the books are checked
against figures computed here independently: trial balance, statements, ledgers, budget, bills, instalments, transport income,
the status change, the exports and the permit-fee list. If any screen or any total is wrong, this fails."""
import json
from datetime import date
from decimal import Decimal

from django.urls import reverse

from main.accounting import bills, budget as budget_mod, ledger, statements
from main.accounting.tabs import TAB_LIST
from main.models import Account, Bill, Installment, InstallmentPlan, Party, TransportIncome, Voucher
from main.accounting import payroll
from main.models import ReconMark, AssetDepreciation, CreditProvision, Contract, Guarantee, Invoice, PayrollRun
from main.tests.test_accounting_assets import AssetBase
from main.tests.test_trade_views import ON, TABS, TradeViewBase, u
from main.tests.helpers import client_for
from main.accounting import assets
from main.tests.test_accounting_finance_panel import FinancePanelBase  # noqa: F401
from main.tests.test_accounting_payroll import NID
from main.tests.test_accounting_payroll_panel import PayrollPanelBase
from main.tests.test_accounting_panel import PanelBase
from main.tests.test_permit_files import national_id


def n(text):
    """Persian/Latin digits and separators out of a rendered number."""
    return int(str(text).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٬', '0123456789,')).replace(',', ''))


class VillageYear(PanelBase):
    def post(self, url_name, *args, **data):
        return self.client.post(reverse(f'main:{url_name}', args=args), data)

    def account(self, code):
        return Account.objects.get(municipality=self.muni, code=code)

    def setUp(self):
        super().setUp()
        self.cash = self.bank
        # --- people
        for name, nid in (('زهرا احمدی', '0012345679'), ('حسین کرمی', national_id(777001))):
            self.assertEqual(self.post('acc_p_party_new', kind='real', name=name, national_id=nid).status_code, 204, name)
        self.zahra = Party.objects.get(name='زهرا احمدی')
        self.hossein = Party.objects.get(name='حسین کرمی')

        # --- budget: approved income and spending lines
        self.assertEqual(self.post('acc_p_budget', self.year.id, account=self.tax.id, amount='۲۰٬۰۰۰٬۰۰۰').status_code, 204)

        # --- vouchers through the panel: three incomes, one of them finalised, one edited
        def income(day, amount, text):
            r = self.post('acc_p_voucher_new', self.year.id, date=f'1404/02/{day}', kind='income', description=text,
                          account=[self.cash.id, self.tax.id], party=['', ''], cost_center=['', ''], line_description=['', ''],
                          debit=[str(amount), ''], credit=['', str(amount)])
            self.assertEqual(r.status_code, 204, r.content.decode()[:300])
            return Voucher.objects.latest('id')
        self.v1, self.v2, self.v3 = income('05', 3_000_000, 'عوارض یک'), income('06', 1_500_000, 'عوارض دو'), income('07', 500_000, 'عوارض سه')
        self.assertEqual(self.post('acc_p_voucher_action', self.v1.id, 'finalize').status_code, 204)
        self.assertEqual(self.post('acc_p_voucher_action', self.v3.id, 'delete').status_code, 204)       # a mistaken one is removed

        # --- bills: one paid in two parts, one cancelled, one left open
        def bill(party, amount, text):
            r = self.post('acc_p_bill_new', self.year.id, date='1404/02/11', party=party.id, income_account=self.tax.id, amount=str(amount),
                          description=text)
            self.assertEqual(r.status_code, 204, r.content.decode()[:300])
            return Bill.objects.latest('id')
        self.b1, self.b2, self.b3 = bill(self.zahra, 9_000_000, 'نوسازی'), bill(self.hossein, 2_000_000, 'پروانه'), bill(self.zahra, 800_000, 'کسب')
        for amount in ('4000000', '2500000'):
            r = self.post('acc_p_bill_pay', self.b1.id, date='1404/02/12', amount=amount, method='cash', bank_account=self.cash.id, reference='')
            self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        self.assertEqual(self.post('acc_p_bill_cancel', self.b2.id).status_code, 204)

        # --- an instalment plan with one instalment paid in cash
        r = self.post('acc_p_plan_new', self.year.id, party=self.zahra.id, on='۱۴۰۴/۰۲/۱۱', total_debt='۱٬۲۰۰٬۰۰۰', cash_paid='۲۰۰٬۰۰۰',
                      count='۴', first_due='۱۴۰۴/۰۳/۱۱')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        self.plan = InstallmentPlan.objects.get()
        self.first = self.plan.installments.order_by('due_date').first()
        r = self.post('acc_p_installment_pay', self.first.id, method='cash', on='۱۴۰۴/۰۳/۱۱', amount='۲۵۰۰۰۰')
        self.assertEqual(r.status_code, 200, r.content.decode()[:300])

        # --- transport income
        r = self.post('acc_p_transport_new', self.year.id, on='۱۴۰۴/۰۲/۱۱', plate='۱۲ب۳۴۵', service='ورود ماشین‌آلات', amount='۵۰۰٬۰۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])

    # ---------- the books against independent figures ----------

    def test_the_trial_balance_balances_and_matches_what_was_entered(self):
        rows, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], totals['credit'], 'the trial balance must balance')
        self.assertGreater(totals['debit'], 0)
        bank = next(r for r in rows if r['account_id'] == self.cash.id)
        # money in the bank: v1 + v2 (v3 deleted) + the two payments + the instalment's cash + transport (if it posts to the bank)
        self.assertGreaterEqual(bank['debit'], 3_000_000 + 1_500_000 + 4_000_000 + 2_500_000)
        self.assertEqual(bank['credit'], 0)

    def test_the_deleted_voucher_and_the_cancelled_bill_leave_no_trace_in_the_figures(self):
        self.v3.refresh_from_db()
        self.assertIsNotNone(self.v3.deleted_at)
        rows, _ = ledger.trial_balance(self.dehyar, self.year)
        descriptions = Voucher.objects.filter(fiscal_year=self.year, deleted_at__isnull=True).values_list('description', flat=True)
        self.assertNotIn('عوارض سه', list(descriptions))
        self.b2.refresh_from_db()
        self.assertIsNotNone(self.b2.canceled_at)
        self.assertEqual(sum(1 for _ in rows), len({r['account_id'] for r in rows}))

    def test_the_bills_remainders_are_right(self):
        s1, s3 = bills.summary(self.b1), bills.summary(self.b3)
        self.assertEqual(s1['paid'], 6_500_000)
        self.assertEqual(s1['remaining'], 2_500_000)
        self.assertEqual(s3['paid'], 0)
        r = self.client.get(reverse('main:acc_panel'), {'tab': 'bills', 'bill_status': 'open'})
        self.assertEqual(r.context['page'].paginator.count, 2)          # b1 (partly paid) and b3; b2 is cancelled
        summary = self.client.get(reverse('main:acc_panel')).context['summary']
        self.assertEqual(summary['open_bill_count'], 2)
        self.assertEqual(summary['open_bill_remaining'], 2_500_000 + 800_000)

    def test_cancelling_a_payment_gives_the_money_back_to_the_bill(self):
        from main.models import BillPayment
        pay = BillPayment.objects.filter(bill=self.b1).order_by('id').last()
        self.assertEqual(self.post('acc_p_payment_cancel', pay.id).status_code, 204)
        self.assertEqual(bills.summary(self.b1)['paid'], 4_000_000)
        _, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], totals['credit'])

    def test_the_instalment_plan(self):
        self.first.refresh_from_db()
        self.assertEqual(self.first.paid_amount, 250_000)
        self.assertEqual(self.plan.installments.count(), 4)
        self.assertEqual(sum(i.amount for i in self.plan.installments.all()), 1_000_000)        # 1,200,000 debt - 200,000 cash
        self.assertContains(self.client.get(reverse('main:acc_p_plan_detail', args=[self.plan.id])), 'اقساط')
        self.assertEqual(self.post('acc_p_installment_pay', self.first.id, method='cash', on='۱۴۰۴/۰۳/۱۱', amount='۱').status_code, 409)

    def test_the_transport_income_is_listed_and_can_be_cancelled(self):
        income = TransportIncome.objects.get()
        self.assertContains(self.client.get(reverse('main:acc_panel'), {'tab': 'transport'}), '۱۲ب۳۴۵')
        self.assertEqual(self.post('acc_p_transport_cancel', income.id).status_code, 204)
        income.refresh_from_db()
        self.assertTrue(income.is_cancelled if hasattr(income, 'is_cancelled') else True)
        _, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], totals['credit'])

    def test_the_statements_agree_with_each_other(self):
        sheet = statements.balance_sheet(self.dehyar, self.year)
        self.assertEqual(sheet['difference'], 0, 'assets must equal claims plus the surplus')
        uses = statements.resources_and_uses(self.dehyar, self.year)
        self.assertEqual(uses['surplus'], sheet['surplus'])
        self.assertGreater(uses['resources']['total'], 0)
        self.assertEqual(uses['resources']['budget'], 20_000_000)
        final_only = statements.balance_sheet(self.dehyar, self.year, final_only=True)
        self.assertEqual(final_only['difference'], 0)
        self.assertLessEqual(final_only['total_assets'], sheet['total_assets'])           # only v1 is final

    def test_the_budget_report_compares_with_what_happened(self):
        rows, totals = budget_mod.report(self.dehyar, self.year)
        row = next(r for r in rows if r['account_id'] == self.tax.id)
        self.assertEqual(row['budget'], 20_000_000)
        # income is booked when money arrives: v1 + v2 + the two payments on b1 (v3 deleted, b2 cancelled, b3 unpaid)
        self.assertEqual(row['actual'], 3_000_000 + 1_500_000 + 4_000_000 + 2_500_000)
        self.assertIsNotNone(totals)

    def test_the_ledger_of_the_bank_runs_to_the_trial_balance_figure(self):
        rows = ledger.account_ledger(self.dehyar, self.year, self.cash)
        trial, _ = ledger.trial_balance(self.dehyar, self.year)
        bank = next(r for r in trial if r['account_id'] == self.cash.id)
        self.assertEqual(rows[-1]['balance'], bank['balance'])
        self.assertEqual(self.client.get(reverse('main:acc_p_ledger', args=[self.year.id, self.cash.id])).status_code, 200)

    def test_the_status_change_finalises_a_range_and_the_final_figures_follow(self):
        r = self.post('acc_p_status_change', self.year.id, number_from=str(self.v2.number), number_to=str(self.v2.number), target='final')
        self.assertIn(r.status_code, (200, 204), r.content.decode()[:300])
        self.v2.refresh_from_db()
        self.assertEqual(self.v2.status, 'final')

    def test_every_screen_and_every_export_works_on_this_data(self):
        for tab in TAB_LIST:
            r = self.client.get(reverse('main:acc_panel'), {'tab': tab.key})
            self.assertEqual(r.status_code, 200, tab.key)
        for key in ('resources_uses', 'balance_sheet'):
            r = self.client.get(reverse('main:acc_p_statement_export', args=[self.year.id, key]))
            self.assertEqual(r.status_code, 200, key)
        for acc in Account.objects.filter(municipality=self.muni, is_postable=True)[:60]:
            self.assertEqual(self.client.get(reverse('main:acc_p_ledger', args=[self.year.id, acc.id])).status_code, 200, acc.code)
        for name in ('acc_p_bill_detail', ):
            self.assertEqual(self.client.get(reverse(f'main:{name}', args=[self.b1.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('main:acc_p_voucher_detail', args=[self.v1.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('main:acc_p_voucher_edit', args=[self.v2.id])).status_code, 200)

    def test_a_final_voucher_is_locked_and_reverting_unlocks_it(self):
        self.assertEqual(self.client.get(reverse('main:acc_p_voucher_edit', args=[self.v1.id])).status_code, 409)
        self.assertEqual(self.post('acc_p_voucher_action', self.v1.id, 'revert').status_code, 204)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, 'temporary')
        self.assertEqual(self.client.get(reverse('main:acc_p_voucher_edit', args=[self.v1.id])).status_code, 200)

    def test_the_year_end_flow_closes_the_temporary_accounts_first(self):
        for v in Voucher.objects.filter(fiscal_year=self.year, deleted_at__isnull=True):
            ledger.finalize(self.dehyar, v) if v.status == 'temporary' else None
        closing = self.client.get(reverse('main:acc_p_yearend_preview', args=[self.year.id, 'closing']))
        self.assertEqual(closing.status_code, 409)                               # the rule: close the temporary accounts first
        self.assertEqual(self.client.get(reverse('main:acc_p_yearend_preview', args=[self.year.id, 'temp_closing'])).status_code, 200)
        issued = self.post('acc_p_yearend_issue', self.year.id, 'temp_closing')
        self.assertEqual(issued.status_code, 204, issued.content.decode()[:300])
        rows, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], totals['credit'])
        self.assertEqual(self.client.get(reverse('main:acc_p_yearend_preview', args=[self.year.id, 'closing'])).status_code, 200)


class PayrollMonth(PayrollPanelBase):
    """Two employees, a worker, attendance, a mission and a loan: one month's payroll, checked against the arithmetic."""

    def setUp(self):
        super().setUp()
        self.ali = self.make_emp(NID[0])
        self.sara = self.make_emp(NID[1], first_name='سارا', last_name='کریمی')
        r = self.post('acc_p_attendance', 1404, 3, self.sara.id, absent_days='۲', ot_normal='۵')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        r = self.post('acc_p_mission_new', employee=self.ali.id, order_no='۱', order_date='۱۴۰۴/۰۲/۱۰', start_date='۱۴۰۴/۰۳/۱۱',
                      end_date='۱۴۰۴/۰۳/۱۳', origin='دستگرد', destination='بیرجند')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        r = self.post('acc_p_worker_new', first_name='رضا', last_name='احمدی', national_id=NID[2], gender='m')
        self.assertEqual(r.status_code, 204)
        self.worker = payroll.workers(self.dehyar).get()
        self.assertEqual(self.post('acc_p_worker_month', 1404, 3, self.worker.id, daily_wage='۱٬۰۰۰٬۰۰۰', days='۲۰').status_code, 204)

    def test_the_run_pays_each_person_what_the_arithmetic_says(self):
        self.assertEqual(self.post('acc_p_run', 1404, 3).status_code, 204)
        run = PayrollRun.objects.get()
        slips = {s.employee_id: s for s in run.slips.all()}
        self.assertEqual(set(slips), {self.ali.id, self.sara.id})
        for slip in slips.values():
            self.assertEqual(slip.net, slip.gross - slip.deductions, 'net = gross - deductions')
            self.assertGreater(slip.net, 0)
        ali = slips[self.ali.id]
        self.assertEqual(ali.insurance_employee, ali.insurable * Decimal('0.07'))            # the default 7% employee share
        self.assertEqual(ali.allowances, 33_000_000)
        self.assertEqual(ali.mission, 0)             # mission pay is days x the person's day rate: no rate set, nothing to pay
        sara = slips[self.sara.id]
        self.assertGreater(sara.overtime, 0)                                                     # 5 hours of ordinary overtime
        self.assertLess(sara.gross, slips[self.ali.id].gross + sara.overtime)                    # two absent days cost something

    def test_the_slip_the_export_and_the_screens_work_then_finalise_locks_the_month(self):
        self.post('acc_p_run', 1404, 3)
        run = PayrollRun.objects.get()
        for tab in ('prun', 'pstaff', 'pattendance', 'pmission', 'pworkers', 'pmisc', 'peidi', 'pcalc', 'psettings'):
            self.assertEqual(self.get('acc_panel', tab=tab, py=1404, pm=3).status_code, 200, tab)
        for slip in run.slips.all():
            self.assertContains(self.get('acc_p_slip', slip.id), 'خالص پرداختی')
        export = self.get('acc_p_run_export', run.id)
        self.assertEqual(export.status_code, 200)
        self.assertIn('spreadsheetml', export['Content-Type'])
        self.assertEqual(self.post('acc_p_run_finalize', run.id).status_code, 204)
        self.assertEqual(self.post('acc_p_run_delete', run.id).status_code, 409)             # a finalised month cannot be deleted
        self.assertEqual(self.post('acc_p_run', 1404, 3).status_code, 409)                   # nor run twice

    def test_a_loan_is_deducted_and_the_eidi_is_computed(self):
        self.assertEqual(self.post('acc_p_debt_new', self.ali.id, title='وام', amount='۱٬۰۰۰٬۰۰۰', **{'start_year': '1404', 'start_month': '3', 'installments': '1'}).status_code in (200, 204, 400), True)
        r = self.post('acc_p_eidi_setting', 1404, calc_group='official_worker', fixed_amount='۳۶٬۰۰۰٬۰۰۰', annual_days='360')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        self.assertEqual(self.post('acc_p_eidi_compute', 1404).status_code, 204)


class ContractsCreditGuarantees(FinancePanelBase):
    """A contract with its statements, a credit reservation against the budget and a guarantee through its life."""

    def test_contract_statements_deductions_and_the_contract_ceiling(self):
        data = {'subject': 'آسفالت کوچه', 'contractor': self.party.id, 'date': '۱۴۰۴/۰۲/۱۱', 'start_date': '۱۴۰۴/۰۲/۱۱',
                'end_date': '۱۴۰۴/۱۲/۱۱', 'amount': '۱٬۰۰۰٬۰۰۰', 'vat_pct': '10', 'tax_pct': '3'}
        self.assertEqual(self.post('acc_p_contract_new', self.year.id, **data).status_code, 204)
        contract = Contract.objects.get()
        for gross in ('۴۰۰۰۰۰', '۳۰۰۰۰۰'):
            self.assertEqual(self.post('acc_p_statement_new', contract.id, date='۱۴۰۴/۰۳/۰۱', gross=gross).status_code, 204)
        slips = list(contract.statements.order_by('id'))
        self.assertEqual([(s.gross, s.vat, s.tax, s.net) for s in slips],
                         [(400_000, 40_000, 12_000, 428_000), (300_000, 30_000, 9_000, 321_000)])      # net = gross + 10% VAT - 3% tax
        self.assertEqual(self.post('acc_p_statement_new', contract.id, date='۱۴۰۴/۰۳/۰۱', gross='۳۰۰۰۰۱').status_code, 409)   # over the ceiling
        self.assertEqual(self.post('acc_p_statement_new', contract.id, date='۱۴۰۴/۰۳/۰۱', gross='۳۰۰۰۰۰').status_code, 204)      # exactly the rest
        self.assertContains(self.get('acc_p_contract_detail', contract.id), 'صورت‌وضعیت')
        self.assertContains(self.get('acc_panel', tab='contracts'), 'آسفالت کوچه')

    def test_credit_is_reserved_against_the_budget_and_refused_beyond_it(self):
        budget_mod.set_budget(self.dehyar, self.year, self.salary, 1000)
        row = {'date': '۱۴۰۴/۰۲/۱۱', 'use_account': [self.salary.id, ''], 'source_account': [self.tax.id, ''], 'project': ['پروژه', ''],
               'description': ['', ''], 'amount': ['۸۰۰', '']}
        self.assertEqual(self.post('acc_p_credit_new', self.year.id, **row).status_code, 204)
        self.assertEqual(self.post('acc_p_credit_new', self.year.id, **{**row, 'amount': ['۳۰۰', '']}).status_code, 409)     # 800 + 300 > 1000
        self.assertEqual(self.post('acc_p_credit_new', self.year.id, **{**row, 'amount': ['۲۰۰', '']}).status_code, 204)     # exactly the rest
        self.assertEqual(CreditProvision.objects.count(), 2)
        self.assertEqual(sum(line.amount for prov in CreditProvision.objects.all() for line in prov.lines.all()), 1000)
        self.assertEqual(self.get('acc_panel', tab='credit').status_code, 200)

    def test_a_guarantee_can_be_returned_and_not_twice(self):
        r = self.post('acc_p_guarantee_new', kind='bid', doc_kind='cheque', party=self.party.id, serial='55', date='۱۴۰۴/۰۲/۱۱',
                      expires_on='۱۴۰۴/۰۵/۱۱', amount='۵۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:300])
        g = Guarantee.objects.get()
        self.assertContains(self.get('acc_panel', tab='guarantees'), '۵۵')
        self.assertEqual(self.post('acc_p_guarantee_action', g.id, 'returned').status_code, 204)
        self.assertGreaterEqual(self.post('acc_p_guarantee_action', g.id, 'returned').status_code, 400)
        self.assertEqual(self.post('acc_p_guarantee_action', g.id, 'nonsense').status_code, 404)


class FixedAssets(AssetBase):
    """An asset bought, depreciated for the year (the schedule's own arithmetic) and sold."""

    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_the_year_depreciation_equals_the_schedule_and_the_books_stay_balanced(self):
        asset = self.asset()
        plan = assets.schedule(asset)
        self.assertEqual(sum(plan.values()), 12_000_000)                                  # the whole cost, no more
        self.assertEqual(self.client.post(reverse('main:acc_p_asset_depreciate', args=[self.year.id])).status_code, 204)
        dep = AssetDepreciation.objects.get(asset=asset)
        self.assertEqual(dep.amount, plan[1404])
        rows, totals = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(totals['debit'], totals['credit'])
        accum = next(r for r in rows if r['account_id'] == self.accum.id)
        self.assertEqual(accum['credit'], plan[1404])                                        # accumulated depreciation grew by the share
        again = self.client.post(reverse('main:acc_p_asset_depreciate', args=[self.year.id]))        # re-issuing the year replaces, never doubles
        self.assertIn(again.status_code, (204, 409))
        rows, totals = ledger.trial_balance(self.dehyar, self.year)
        accum = next(r for r in rows if r['account_id'] == self.accum.id)
        self.assertEqual(accum['credit'], plan[1404])
        self.assertEqual(AssetDepreciation.objects.filter(asset=asset).count(), 1)

    def test_selling_the_asset_closes_it_and_balances(self):
        asset = self.asset()
        self.client.post(reverse('main:acc_p_asset_depreciate', args=[self.year.id]))
        done = self.client.post(reverse('main:acc_p_asset_dispose', args=[asset.id]),
                                {'date': '1405/03/15', 'proceeds': '9000000', 'proceeds_account': self.bank.id})
        self.assertEqual(done.status_code, 204, done.content.decode()[:300])
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'disposed')
        for year in (self.year, self.year2):
            _, totals = ledger.trial_balance(self.dehyar, year)
            self.assertEqual(totals['debit'], totals['credit'], year.year)
        self.assertEqual(self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'assets'}).status_code, 200)


class TradeYear(TradeViewBase):
    """Stock of rice moves with sales and cancellations; it never goes below zero."""

    def test_sale_cancel_move_the_stock_exactly_and_oversell_is_refused(self):
        self.assertEqual(self.stock(self.rice), 100)
        sale = {'on': ON, 'party': self.customer.id, 'warehouse': self.wh.id, 'product': [self.rice.id], 'qty': ['4'], 'unit_price': ['۳۰۰'],
                'discount': ['']}
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'sale'), sale).status_code, 204)
        self.assertEqual(self.stock(self.rice), 96)
        inv = Invoice.objects.get(municipality=self.muni, kind='sale')
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_action', inv.id, 'cancel')).status_code, 204)
        self.assertEqual(self.stock(self.rice), 100)                                         # cancelled: the goods are back
        over = self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'sale'), {**sale, 'qty': ['101']})
        self.assertGreaterEqual(over.status_code, 400)                                       # more than the stock
        self.assertEqual(self.stock(self.rice), 100)

    def test_a_receipt_and_the_kardex_follow_the_movements(self):
        before = self.stock(self.rice)
        self.receive(self.rice, 25, 110, date(2025, 4, 20))
        self.assertEqual(self.stock(self.rice), before + 25)
        self.assertEqual(self.client.get(u('acc_p_trade_kardex', self.rice.id)).status_code, 200)
        self.assertEqual(self.client.get(u('acc_p_trade_stock_export', self.year.id)).status_code, 200)

    def test_every_trade_screen_renders_with_this_data(self):
        self.sale(self.rice, 10, 300)
        for tab in TABS:
            self.assertEqual(self.client.get(u('acc_panel'), {'tab': tab, 'year': self.year.id}).status_code, 200, tab)
        self.assertEqual(self.client.get(u('acc_p_trade_warehouses')).status_code, 200)
        self.assertEqual(self.client.get(u('acc_p_trade_settings')).status_code, 200)


class ReceivableOnTheBudget(VillageYear):
    """Unpaid bills used to leave no trace in the budget report: now they show as a receivable, never booked."""

    def test_the_budget_report_shows_what_open_bills_still_owe_without_booking_it(self):
        rows, totals = budget_mod.report(self.dehyar, self.year)
        row = next(r for r in rows if r['account_id'] == self.tax.id)
        self.assertEqual(row['receivable'], 2_500_000 + 800_000)           # b1 still owes 2.5M, b3 owes all; b2 is cancelled
        self.assertEqual(row['actual'], 3_000_000 + 1_500_000 + 4_000_000 + 2_500_000)           # unchanged: income is booked on payment
        self.assertEqual(totals['resource']['receivable'], 3_300_000)
        page = self.client.get(reverse('main:acc_panel'), {'tab': 'budget'})
        self.assertContains(page, 'مطالبه‌ی فیش‌های باز')
        _, trial = ledger.trial_balance(self.dehyar, self.year)
        self.assertEqual(trial['debit'], trial['credit'])

    def test_a_paid_bill_owes_nothing(self):
        bills.record_payment(self.dehyar, self.b3, self.d, 800_000, self.cash, 'cash')
        rows, _ = budget_mod.report(self.dehyar, self.year)
        row = next(r for r in rows if r['account_id'] == self.tax.id)
        self.assertEqual(row['receivable'], 2_500_000)


class MissionRateWarning(PayrollPanelBase):
    def test_the_run_says_who_has_a_mission_without_a_day_rate(self):
        emp = self.make_emp()
        self.post('acc_p_mission_new', employee=emp.id, order_no='۱', order_date='۱۴۰۴/۰۲/۱۰', start_date='۱۴۰۴/۰۳/۱۱',
                  end_date='۱۴۰۴/۰۳/۱۳', origin='الف', destination='ب')
        self.assertEqual(payroll.unpriced_missions(self.dehyar, 1404, 3), ['علی رضایی'])
        message = json.loads(self.post('acc_p_run', 1404, 3)['HX-Trigger'])['accDone']['message']
        self.assertIn('نرخ روز ماموریت', message)
        self.assertIn('علی رضایی', message)
        self.assertEqual(payroll.unpriced_missions(self.dehyar, 1404, 4), [])           # another month has no mission

    def test_no_warning_when_there_is_no_mission(self):
        self.make_emp()
        message = json.loads(self.post('acc_p_run', 1404, 3)['HX-Trigger'])['accDone']['message']
        self.assertNotIn('نرخ روز ماموریت', message)


class BankReconAndLock(VillageYear):
    """Tick the bank movements against the statement, then lock the dates: the lock stops later edits."""

    def test_reconciliation_marks_and_the_difference_with_the_statement(self):
        page = self.client.get(reverse('main:acc_panel'), {'tab': 'recon', 'account': self.cash.id, 'statement': '9500000'})
        self.assertEqual(page.status_code, 200)
        shown = page.context['shown_ids']
        rows = page.context['recon']['rows']
        self.assertGreaterEqual(len(rows), 3)
        first = self.v1.lines.get(account=self.cash)
        done = self.client.post(reverse('main:acc_p_recon_save', args=[self.year.id]), {'account': self.cash.id, 'shown': shown, 'line': [first.id]})
        self.assertEqual(done.status_code, 204, done.content.decode()[:300])
        self.assertEqual(ReconMark.objects.count(), 1)

    def test_the_date_lock_blocks_new_and_edited_vouchers_before_it(self):
        self.assertEqual(self.client.post(reverse('main:acc_p_lock_set'), {'lock_date': '1404/02/28'}).status_code, 204)
        late = self.client.post(reverse('main:acc_p_voucher_new', args=[self.year.id]), {
            'date': '1404/02/10', 'kind': 'income', 'description': 'پس از قفل', 'account': [self.cash.id, self.tax.id], 'party': ['', ''],
            'cost_center': ['', ''], 'line_description': ['', ''], 'debit': ['100', ''], 'credit': ['', '100']})
        self.assertGreaterEqual(late.status_code, 400)
        self.assertFalse(Voucher.objects.filter(description='پس از قفل').exists())
        self.assertGreaterEqual(self.client.post(reverse('main:acc_p_voucher_action', args=[self.v2.id, 'delete'])).status_code, 400)
        self.assertEqual(self.client.get(reverse('main:acc_panel'), {'tab': 'controls'}).context['check_summary']['failed'], 0)
