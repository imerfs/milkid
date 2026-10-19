"""Calculators, global search and printable cheques of the accountant workspace."""
from datetime import date

from django.template import Context, Template
from django.test import SimpleTestCase
from django.urls import reverse

from main.accounting import access_levels, search, tools
from main.models import Account, Contract, FiscalYear, InstallmentPlan, Party, PayableDocument
from main.office.errors import Invalid
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase, line, make_user
from main.accounting import ledger


class NumberToWordsTests(SimpleTestCase):
    def test_known_values(self):
        cases = {0: 'صفر', 1: 'یک', 11: 'یازده', 20: 'بیست', 21: 'بیست و یک', 100: 'صد', 101: 'صد و یک', 999: 'نهصد و نود و نه',
                 1000: 'یک هزار', 12345: 'دوازده هزار و سیصد و چهل و پنج', 100000: 'صد هزار',
                 1234567: 'یک میلیون و دویست و سی و چهار هزار و پانصد و شصت و هفت', 2_000_000_000: 'دو میلیارد',
                 10 ** 12: 'یک تریلیون', 10 ** 15 + 5: 'یک کوادریلیون و پنج', -5: 'منفی پنج'}
        for number, words in cases.items():
            with self.subTest(number=number):
                self.assertEqual(tools.number_to_words(number), words)

    def test_limits(self):
        for bad in (10 ** 18, 1.5, True):
            with self.assertRaises(Invalid):
                tools.number_to_words(bad)
        self.assertTrue(tools.number_to_words(10 ** 18 - 1))

    def test_template_filter(self):
        out = Template('{% load accounting_tags %}{{ n|words }}|{{ x|words }}').render(Context({'n': 250000, 'x': 'abc'}))
        self.assertEqual(out, 'دویست و پنجاه هزار|')


class DateAndLoanTests(SimpleTestCase):
    def test_dates_both_ways(self):
        self.assertEqual(tools.convert_date(jalali='1404/05/01')['gregorian'], '2025-07-23')
        self.assertEqual(tools.convert_date(gregorian='2025-07-23')['jalali'], '1404/05/01')
        self.assertEqual(tools.convert_date(jalali='۱۴۰۴/۰۵/۰۱')['gregorian'], '2025-07-23')
        for bad in ({}, {'jalali': '1404/13/40'}, {'gregorian': 'x'}, {'jalali': 'abc'}):
            with self.assertRaises(Invalid):
                tools.convert_date(**bad)

    def test_loan_table_ends_at_zero_and_adds_up(self):
        out = tools.loan(12_000_000, 18, 12)
        self.assertEqual((out['payment'], out['count']), (1_100_160, 12))
        self.assertEqual(out['schedule'][-1]['balance'], 0)
        self.assertEqual(sum(r['principal'] for r in out['schedule']), 12_000_000)
        self.assertEqual(out['total'], sum(r['payment'] for r in out['schedule']))
        self.assertEqual(out['interest'], out['total'] - 12_000_000)

    def test_interest_free_loan_splits_evenly_with_the_remainder_last(self):
        out = tools.loan(1_000_000, 0, 3)
        self.assertEqual([r['payment'] for r in out['schedule']], [333_333, 333_333, 333_334])

    def test_loan_rejects_nonsense_and_can_limit_rows(self):
        for args in ((0, 10, 12), (1000, -1, 12), (1000, 10, 0), (1000, 10, 361), (1000.5, 10, 12), ('x', 1, 1)):
            with self.assertRaises(Invalid):
                tools.loan(*args)
        self.assertEqual(len(tools.loan(1_000_000, 10, 24, rows=5)['schedule']), 5)


class ToolsPanelTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_endpoints_answer_json(self):
        words = self.client.get(reverse('main:acc_p_tools_words'), {'n': '۱۲٬۳۴۵'}).json()
        self.assertEqual(words['words'], 'دوازده هزار و سیصد و چهل و پنج')
        self.assertEqual(self.client.get(reverse('main:acc_p_tools_words'), {'n': 'x'}).json()['error'], 'یک عدد صحیح وارد کنید.')
        date_ = self.client.get(reverse('main:acc_p_tools_date'), {'jalali': '1404/05/01'}).json()
        self.assertEqual(date_['gregorian'], '2025-07-23')
        self.assertEqual(self.client.get(reverse('main:acc_p_tools_date')).status_code, 400)
        loan = self.client.get(reverse('main:acc_p_tools_loan'), {'amount': '۱۲٬۰۰۰٬۰۰۰', 'rate': '18', 'months': '12', 'rows': '3'}).json()
        self.assertEqual((loan['payment'], len(loan['schedule'])), (1_100_160, 3))
        self.assertEqual(self.client.get(reverse('main:acc_p_tools_loan'), {'amount': '0', 'months': '3'}).status_code, 400)

    def test_tab_calculator_and_help_render(self):
        tab = self.client.get(reverse('main:acc_panel'), {'tab': 'tools'})
        self.assertContains(tab, 'عدد به حروف')
        self.assertContains(self.client.get(reverse('main:acc_p_calculator')), 'data-calc-root')
        self.assertContains(self.client.get(reverse('main:acc_p_shortcuts')), 'Alt')

    def test_anonymous_and_citizens_are_kept_out(self):
        for who in (client_for(), client_for(make_user('citizen'))):
            self.assertIn(who.get(reverse('main:acc_p_tools_words'), {'n': '5'}).status_code, (302, 403))
            self.assertIn(who.get(reverse('main:acc_p_search'), {'q': 'abc'}).status_code, (302, 403))


class SearchTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)
        self.party = Party.objects.create(municipality=self.muni, name='حسین رضایی', national_id='0012345678', mobile='09151234567')
        self.v = self.voucher(1000)
        from main.accounting import bills
        self.bill = bills.issue_bill(self.dehyar, self.year, self.d, self.party, self.tax, 5000, 'عوارض پروانه')

    def kinds(self, q):
        return {r['kind'] for r in search.run(self.dehyar, q)}

    def test_each_kind_is_found(self):
        self.assertIn('سند', self.kinds('عوارض'))
        self.assertIn('طرف حساب', self.kinds('رضایی'))
        self.assertIn('طرف حساب', self.kinds('09151'))
        self.assertIn('حساب', self.kinds('بانک'))
        self.assertIn('فیش', self.kinds('پروانه'))

    def test_numbers_find_vouchers_and_bills(self):
        hits = [r for r in search.run(self.dehyar, str(self.v.number).zfill(2)) if r['kind'] == 'سند']
        self.assertTrue(hits)
        persian = str(self.bill.number).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')).rjust(2, '۰')
        self.assertIn('فیش', {r['kind'] for r in search.run(self.dehyar, persian)})

    def test_short_queries_return_nothing_and_results_say_how_to_open(self):
        self.assertEqual(search.run(self.dehyar, 'ع'), [])
        modal = next(r for r in search.run(self.dehyar, 'عوارض') if r['kind'] == 'سند')
        self.assertEqual((modal['action'], modal['url']), ('modal', reverse('main:acc_p_voucher_detail', args=[self.v.id])))
        tab = next(r for r in search.run(self.dehyar, 'رضایی') if r['kind'] == 'طرف حساب')
        self.assertEqual((tab['action'], tab['tab']), ('tab', 'parties'))

    def test_other_municipalities_are_not_searched(self):
        from main.tests.helpers import make_municipality
        other = make_user('dehyari')
        make_municipality(other)
        self.assertEqual(search.run(other, 'رضایی'), [])

    def test_closed_areas_are_left_out_for_the_accountant(self):
        accountant = make_user('accountant', city_village=self.muni.city_village)
        access_levels.save_rules(self.dehyar, {'vouchers': 'none', 'master': 'none'})
        kinds = {r['kind'] for r in search.run(accountant, 'عوارض')}
        self.assertEqual(kinds, {'فیش'})

    def test_endpoint(self):
        data = self.client.get(reverse('main:acc_p_search'), {'q': 'رضایی'}).json()
        self.assertEqual(data['results'][0]['kind'], 'طرف حساب')


class PrintTests(LedgerBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)
        self.party = Party.objects.create(municipality=self.muni, name='پیمانکار نمونه')
        self.doc = PayableDocument.objects.create(
            municipality=self.muni, fiscal_year=self.year, kind='cheque', serial='123456', party=self.party, bank_account=self.bank,
            issue_date=self.d, due_date=date(2025, 8, 1), amount=2_500_000, description='بابت پروژه')

    def test_cheque_print_has_amount_in_digits_and_words_and_the_chosen_paper(self):
        page = self.client.get(reverse('main:acc_p_print_cheque', args=[self.doc.id]))
        self.assertContains(page, 'پیمانکار نمونه')
        self.assertContains(page, 'دو میلیون و پانصد هزار ریال')
        self.assertContains(page, 'size: 175mm 80mm')
        a4 = self.client.get(reverse('main:acc_p_print_cheque', args=[self.doc.id]), {'paper': 'a4'})
        self.assertContains(a4, 'size: 210mm 297mm')
        junk = self.client.get(reverse('main:acc_p_print_cheque', args=[self.doc.id]), {'paper': 'evil'})
        self.assertContains(junk, 'size: 175mm 80mm')

    def test_other_municipalities_cannot_print_it(self):
        from main.tests.helpers import make_municipality
        other = make_user('dehyari')
        make_municipality(other)
        self.assertEqual(client_for(other).get(reverse('main:acc_p_print_cheque', args=[self.doc.id])).status_code, 404)

    def test_detail_modal_links_to_the_print_page(self):
        page = self.client.get(reverse('main:acc_p_payable_detail', args=[self.doc.id]))
        self.assertContains(page, reverse('main:acc_p_print_cheque', args=[self.doc.id]))

    def test_deposit_slip_for_a_received_cheque(self):
        from main.models import Installment
        plan = InstallmentPlan.objects.create(municipality=self.muni, fiscal_year=self.year, number=1, date=self.d, party=self.party,
                                              total_debt=900_000, cash_paid=0, plan_amount=900_000, count=3)
        inst = Installment.objects.create(plan=plan, seq=1, due_date=date(2025, 9, 1), amount=300_000, method='cheque', bank='ملی',
                                          serial='555', owner_name='صاحب حساب', cheque_date=date(2025, 9, 1))
        page = self.client.get(reverse('main:acc_p_print_slip', args=[inst.id]))
        self.assertContains(page, 'سیصد هزار ریال')
        self.assertContains(page, 'size: 148mm 210mm')
        self.assertContains(self.client.get(reverse('main:acc_p_cheque_detail', args=[inst.id])), reverse('main:acc_p_print_slip', args=[inst.id]))


class ChequeSearchTests(LedgerBase):
    def setUp(self):
        super().setUp()
        from datetime import timedelta
        from main.models import Installment
        self.party = Party.objects.create(municipality=self.muni, name='پیمانکار')
        self.doc = PayableDocument.objects.create(
            municipality=self.muni, fiscal_year=self.year, kind='cheque', serial='765432', party=self.party, bank_account=self.bank,
            issue_date=self.d, due_date=self.d + timedelta(days=30), amount=2_000_000)
        plan = InstallmentPlan.objects.create(municipality=self.muni, fiscal_year=self.year, number=1, date=self.d, party=self.party,
                                              total_debt=900_000, cash_paid=0, plan_amount=900_000, count=3)
        self.cheque = Installment.objects.create(plan=plan, seq=1, due_date=self.d, amount=300_000, method='cheque', serial='998877',
                                                 series='12/ب', owner_name='صاحب حساب')

    def test_issued_and_received_cheques_are_found_by_their_number(self):
        issued = [r for r in search.run(self.dehyar, '765432') if r['kind'] == 'چک پرداختی']
        self.assertEqual(issued[0]['url'], reverse('main:acc_p_payable_detail', args=[self.doc.id]))
        received = [r for r in search.run(self.dehyar, '998877') if r['kind'] == 'چک دریافتی']
        self.assertEqual(received[0]['url'], reverse('main:acc_p_cheque_detail', args=[self.cheque.id]))
        persian = '۹۹۸۸۷۷'
        self.assertTrue([r for r in search.run(self.dehyar, persian) if r['kind'] == 'چک دریافتی'])

    def test_other_municipalities_and_closed_areas_do_not_leak_cheques(self):
        other = make_user('dehyari')
        from main.tests.helpers import make_municipality
        make_municipality(other)
        self.assertEqual(search.run(other, '765432'), [])
        accountant = make_user('accountant', city_village=self.muni.city_village)
        access_levels.save_rules(self.dehyar, {'contracts': 'none'})
        kinds = {r['kind'] for r in search.run(accountant, '765432')}
        self.assertNotIn('چک پرداختی', kinds)
