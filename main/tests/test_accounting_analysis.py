"""Report builder, pivot analyser and charts."""
from datetime import date

from django.urls import reverse

from main.accounting import bills, builder, charts, ledger
from main.models import Party
from main.office.errors import Invalid
from main.tests.helpers import client_for, isolate_private_media
from main.tests.test_accounting_ledger import LedgerBase, line


class BuilderBase(LedgerBase):
    def setUp(self):
        isolate_private_media(self)
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='آقای الف')
        self.other = Party.objects.create(municipality=self.muni, name='خانم ب')
        self.voucher(1000, on=date(2025, 4, 25))                                  # 1404/02/05
        self.voucher(500, on=date(2025, 4, 26))
        self.voucher(250, on=date(2025, 6, 1))                                    # 1404/03/11
        ledger.create_voucher(self.dehyar, self.year, date(2025, 6, 2), 'expense', 'حقوق',
                              [line(self.salary, debit=300), line(self.bank, credit=300)])


class BuilderTests(BuilderBase):
    def test_group_by_account_sums_the_measure(self):
        out = builder.build(self.dehyar, self.year, 'lines', 'account', measure='debit')
        by_label = {row[0]: row[1] for row in out['rows']}
        self.assertEqual(by_label['1120101 - بانک ملی'], 1750)
        self.assertEqual(by_label['6010101001 - حقوق دهیار'], 300)
        self.assertEqual(out['totals'][1], 2050)

    def test_months_are_jalali_months(self):
        out = builder.build(self.dehyar, self.year, 'lines', 'month', measure='credit')
        self.assertEqual([r[0] for r in out['rows']], ['1404/02 اردیبهشت', '1404/03 خرداد'])
        self.assertEqual([r[1] for r in out['rows']], [1500, 550])

    def test_pivot_rows_by_account_and_columns_by_month(self):
        out = builder.build(self.dehyar, self.year, 'lines', 'account', column='month', measure='debit')
        self.assertEqual(out['columns'], ['حساب', '1404/02 اردیبهشت', '1404/03 خرداد', 'جمع'])
        bank = next(r for r in out['rows'] if r[0].startswith('1120101'))
        self.assertEqual(bank[1:], [1500, 250, 1750])

    def test_date_range_and_status_filters(self):
        out = builder.build(self.dehyar, self.year, 'lines', 'account', measure='credit', date_from=date(2025, 6, 1))
        self.assertEqual(out['totals'][1], 550)
        ledger.finalize(self.dehyar, self.year.vouchers.first())
        final = builder.build(self.dehyar, self.year, 'lines', 'account', measure='count', final_only=True)
        self.assertEqual(final['totals'][1], 2)

    def test_counts_are_not_money(self):
        out = builder.build(self.dehyar, self.year, 'lines', 'kind', measure='count')
        self.assertEqual(out['money'], set())
        self.assertEqual({r[0]: r[1] for r in out['rows']}, {'درآمد': 6, 'هزینه': 2})

    def test_other_datasets(self):
        bill = bills.issue_bill(self.dehyar, self.year, date(2025, 5, 1), self.party, self.tax, 1000, 'عوارض')
        bills.record_payment(self.dehyar, bill, date(2025, 5, 2), 400, self.bank, 'cash')
        paid = builder.build(self.dehyar, self.year, 'payments', 'method', measure='amount')
        self.assertEqual(paid['rows'], [['نقد', 400]])
        self.assertEqual(builder.build(self.dehyar, self.year, 'bills', 'party', measure='amount')['rows'], [['آقای الف', 1000]])
        self.assertEqual(builder.build(self.dehyar, self.year, 'plans', 'party')['rows'], [])

    def test_bad_choices_are_refused(self):
        for kwargs in ({'dataset': 'nope', 'group': 'account'}, {'dataset': 'lines', 'group': 'nope'},
                       {'dataset': 'lines', 'group': 'account', 'measure': 'nope'},
                       {'dataset': 'lines', 'group': 'account', 'column': 'nope'}):
            with self.assertRaises(Invalid):
                builder.build(self.dehyar, self.year, kwargs.pop('dataset'), kwargs.pop('group'), **kwargs)

    def test_only_the_actors_municipality_is_read(self):
        from main.tests.helpers import make_municipality
        from main.tests.test_accounting_ledger import make_user
        other = make_user('dehyari')
        make_municipality(other)
        year = ledger.open_year(other, 1404)
        self.assertEqual(builder.build(other, year, 'lines', 'account')['rows'], [])

    def test_the_catalogue_lists_every_dataset(self):
        self.assertEqual(set(builder.catalogue()), set(builder.DATASETS))


class ChartTests(BuilderBase):
    def test_monthly_resources_and_uses_and_budget_totals(self):
        data = charts.data(self.dehyar, self.year)
        self.assertEqual((data['resources'][1], data['resources'][2]), (1500, 250))     # اردیبهشت, خرداد
        self.assertEqual(data['uses'][2], 300)
        self.assertEqual(data['top_uses']['actual'], [300])
        self.assertEqual(data['top_resources']['labels'], ['عوارض'])
        self.assertEqual(data['budget_vs_actual']['actual'], [1750, 300])
        self.assertEqual(len(data['months']), 12)

    def test_closing_vouchers_do_not_remove_the_year_from_the_chart(self):
        from main.accounting import yearend
        from main.models import Account
        Account.objects.create(municipality=self.muni, code='410', title='مازاد', kind='equity', nature='credit')
        yearend.issue(self.dehyar, self.year, 'temp_closing')
        self.assertEqual(sum(charts.data(self.dehyar, self.year)['resources']), 1750)

    def test_panel_tabs_exports_and_data_endpoint(self):
        client = client_for(self.dehyar)
        tab = lambda name, **p: client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': name, **p})
        page = tab('builder', dataset='lines', group='account', measure='debit')
        self.assertEqual(page.context['report']['totals'][1]['v'], 2050)
        self.assertContains(tab('builder', date_from='x'), 'تاریخ')
        self.assertContains(tab('charts'), 'منابع و مصارف ماهانه')
        export = client.get(reverse('main:acc_p_builder_export', args=[self.year.id]), {'dataset': 'lines', 'group': 'month'})
        self.assertEqual(export.status_code, 200)
        data = client.get(reverse('main:acc_p_chart_data', args=[self.year.id]))
        self.assertEqual(data.json()['resources'][1], 1500)
        self.assertEqual(client.get(reverse('main:acc_p_builder_export', args=[self.year.id]), {'date_to': 'x'}).status_code, 400)


class MoreDatasetTests(BuilderBase):
    def test_contracts_statements_payables_and_transport(self):
        from datetime import timedelta
        from main.accounting import contracts, transport, treasury
        contract = contracts.create_contract(
            self.dehyar, self.year, subject='آسفالت', contractor=self.party, date=self.d, start_date=self.d,
            end_date=self.d + timedelta(days=200), amount=1_000_000, vat_pct=10, good_performance_pct=5,
            contractor_insurance_pct=7, employer_insurance_pct=16, tax_pct=3)
        contracts.add_statement(self.dehyar, contract, self.d + timedelta(days=10), 200_000)
        treasury.issue(self.dehyar, self.year, kind='cheque', serial='11', party=self.party, bank_account=self.bank,
                       issue_date=self.d, due_date=self.d + timedelta(days=30), amount=4000)
        transport.record(self.dehyar, self.year, on=self.d, plate='11ب111', service='عوارض خودرو', amount=700)
        self.assertEqual(builder.build(self.dehyar, self.year, 'contracts', 'contractor', measure='amount')['rows'],
                         [['آقای الف', 1_000_000]])
        statements = builder.build(self.dehyar, self.year, 'statements', 'contractor', measure='gross')
        self.assertEqual(statements['rows'], [['آقای الف', 200_000]])
        self.assertEqual(builder.build(self.dehyar, self.year, 'payables', 'status')['rows'], [['صادر شده', 4000]])
        self.assertEqual(builder.build(self.dehyar, self.year, 'transport', 'service')['rows'], [['عوارض خودرو', 700]])

    def test_payroll_slips_by_employee_group_and_month(self):
        from main.accounting import payroll
        from main.tests.test_accounting_payroll import NID
        employee = payroll.add_employee(self.dehyar, first_name='علی', last_name='رضایی', national_id=NID[0],
                                        calc_group='official_worker', list_title='کارگران رسمی', job_title='کارگر',
                                        start_date=date(2024, 1, 1))
        payroll.set_allowances(self.dehyar, employee, {1: 30_000_000})
        payroll.run_payroll(self.dehyar, 1404, 3)
        payroll.run_payroll(self.dehyar, 1404, 4)
        by_employee = builder.build(self.dehyar, self.year, 'payroll', 'employee', measure='net')
        self.assertEqual([r[0] for r in by_employee['rows']], ['علی رضایی'])
        self.assertGreater(by_employee['totals'][1], 0)
        by_month = builder.build(self.dehyar, self.year, 'payroll', 'month', measure='count')
        self.assertEqual([r[0] for r in by_month['rows']], ['1404/03 خرداد', '1404/04 تیر'])
        pivot = builder.build(self.dehyar, self.year, 'payroll', 'group', column='month', measure='gross')
        self.assertEqual(pivot['columns'], ['گروه محاسباتی', '1404/03 خرداد', '1404/04 تیر', 'جمع'])
        only_tir = builder.build(self.dehyar, self.year, 'payroll', 'month', measure='count', date_from=date(2025, 6, 25))
        self.assertEqual([r[0] for r in only_tir['rows']], ['1404/04 تیر'])
        self.assertEqual(builder.build(self.dehyar, self.year, 'payroll', 'month', measure='count', final_only=True)['rows'], [])
