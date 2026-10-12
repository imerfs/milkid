"""Accounting workspace on the accountant dashboard: HTMX fragments, modal forms, same rules and tenant isolation."""
import json
from datetime import date

from django.urls import reverse

from main.accounting import bills, budget, ledger
from main.models import Account, Bill, BillPayment, Party, Voucher
from main.tests.helpers import client_for, make_municipality, make_user as _make_user
from main.tests.test_accounting_views import AccountingPagesBase, make_user


def trigger(response):
    return json.loads(response['HX-Trigger'])


class PanelBase(AccountingPagesBase):
    def setUp(self):
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='علی رضایی', national_id='0499370899')
        self.d = date(2025, 5, 1)

    def voucher(self, amount=1000, status='temporary'):
        v = ledger.create_voucher(self.dehyar, self.year, self.d, 'income', 'عوارض آزمون',
                                  [{'account': self.bank, 'debit': amount, 'credit': 0},
                                   {'account': self.tax, 'debit': 0, 'credit': amount}])
        if status == 'final':
            ledger.finalize(self.dehyar, v)
        return v

    def bill(self, amount=1000):
        return bills.issue_bill(self.dehyar, self.year, self.d, self.party, self.tax, amount, 'عوارض نوسازی')


class PanelTests(PanelBase):
    def get(self, **params):
        return self.client.get(reverse('main:acc_panel'), params)

    def test_summary_cards_count_real_rows(self):
        self.voucher()
        self.voucher(status='final')
        b = self.bill(5000)
        bills.record_payment(self.dehyar, b, self.d, 2000, self.bank, 'cash')
        self.bill(700)
        r = self.get()
        self.assertEqual(r.status_code, 200)
        s = r.context['summary']
        self.assertEqual((s['final_count'], s['open_bill_count'], s['open_bill_remaining']), (1, 2, 3000 + 700))
        self.assertEqual(s['temporary_count'], 2)  # the temporary one plus the payment's income voucher

    def test_each_tab_renders_and_filters(self):
        self.voucher()
        self.bill(), self.bill(900)
        self.assertContains(self.get(tab='vouchers', q='آزمون'), 'عوارض آزمون')
        self.assertNotContains(self.get(tab='vouchers', q='چیز دیگر'), 'عوارض آزمون')
        self.assertEqual(self.get(tab='vouchers', status='final').context['page'].paginator.count, 0)
        self.assertEqual(self.get(tab='bills').context['page'].paginator.count, 2)
        self.assertEqual(self.get(tab='bills', q='رضایی', bill_status='open').context['page'].paginator.count, 2)
        self.assertEqual(self.get(tab='bills', bill_status='paid').context['page'].paginator.count, 0)
        self.assertContains(self.get(tab='budget'), 'جمع منابع')

    def test_unpaid_bill_offers_payment_not_just_view(self):
        self.bill()
        self.assertContains(self.get(tab='bills'), 'ثبت پرداخت')

    def test_no_year_shows_setup_tab_and_foreign_year_is_not_shown(self):
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        r = c.get(reverse('main:acc_panel'))
        self.assertContains(r, 'سال مالی‌ای باز نشده')
        self.assertContains(r, reverse('main:acc_p_year_open'))
        self.assertEqual(r.context['tab'], 'setup')
        r = c.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'vouchers'})
        self.assertEqual((r.context['year'], r.context['tab']), (None, 'setup'))
        self.assertContains(r, 'سال مالی انتخاب‌شده پیدا نشد')

    def test_closed_year_hides_operation_buttons(self):
        self.year.is_closed = True
        self.year.save()
        html = self.get().content.decode()
        self.assertNotIn(reverse('main:acc_p_voucher_new', args=[self.year.id]), html)
        self.assertIn('سال بسته است', html)

    def test_dashboard_embeds_the_workspace_and_loads_it(self):
        acc = make_user('accountant', city_village=self.muni.city_village)
        html = client_for(acc).get(reverse('main:accountant_dashboard')).content.decode()
        self.assertIn('id="acc-panel"', html)
        self.assertIn(f'hx-get="{reverse("main:acc_panel")}"', html)


class AccessTests(PanelBase):
    def test_anonymous_and_citizen_cannot_use_any_fragment(self):
        v, b = self.voucher(), self.bill()
        urls = [reverse('main:acc_panel'), reverse('main:acc_p_voucher_new', args=[self.year.id]),
                reverse('main:acc_p_voucher_detail', args=[v.id]), reverse('main:acc_p_bill_new', args=[self.year.id]),
                reverse('main:acc_p_bill_detail', args=[b.id]), reverse('main:acc_p_budget', args=[self.year.id])]
        for who in (client_for(), client_for(make_user('citizen'))):
            for url in urls:
                self.assertEqual(who.get(url).status_code, 302, url)

    def test_other_municipality_gets_404_and_nothing_changes(self):
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        v, b = self.voucher(), self.bill()
        pay = bills.record_payment(self.dehyar, b, self.d, 100, self.bank, 'cash')
        for name, args in [('acc_p_voucher_new', [self.year.id]), ('acc_p_voucher_detail', [v.id]),
                           ('acc_p_voucher_edit', [v.id]), ('acc_p_bill_new', [self.year.id]),
                           ('acc_p_bill_detail', [b.id]), ('acc_p_budget', [self.year.id])]:
            self.assertEqual(c.get(reverse(f'main:{name}', args=args)).status_code, 404, name)
        posts = [reverse('main:acc_p_voucher_action', args=[v.id, a]) for a in ('finalize', 'revert', 'delete')]
        posts += [reverse('main:acc_p_bill_pay', args=[b.id]), reverse('main:acc_p_bill_cancel', args=[b.id]),
                  reverse('main:acc_p_payment_cancel', args=[pay.id]), reverse('main:acc_p_bill_new', args=[self.year.id]),
                  reverse('main:acc_p_voucher_new', args=[self.year.id]), reverse('main:acc_p_budget', args=[self.year.id])]
        for url in posts:
            self.assertEqual(c.post(url, {'amount': '5'}).status_code, 404, url)
        v.refresh_from_db()
        self.assertEqual((v.status, v.deleted_at), ('temporary', None))
        self.assertTrue(BillPayment.objects.filter(pk=pay.pk).exists())

    def test_actions_need_post(self):
        v = self.voucher()
        self.assertEqual(self.client.get(reverse('main:acc_p_voucher_action', args=[v.id, 'delete'])).status_code, 405)
        self.assertEqual(self.client.get(reverse('main:acc_p_bill_pay', args=[self.bill().id])).status_code, 405)

    def test_unknown_voucher_action_is_404(self):
        v = self.voucher()
        self.assertEqual(self.client.post(reverse('main:acc_p_voucher_action', args=[v.id, 'purge'])).status_code, 404)


class VoucherModalTests(PanelBase):
    def data(self, debit='1000', credit='1000', **extra):
        return {'date': '1404/02/11', 'kind': 'income', 'description': 'عوارض',
                'account': [self.bank.id, self.tax.id], 'party': ['', ''], 'cost_center': ['', ''],
                'line_description': ['', ''], 'debit': [debit, ''], 'credit': ['', credit], **extra}

    def test_form_opens_with_todays_year_accounts(self):
        r = self.client.get(reverse('main:acc_p_voucher_new', args=[self.year.id]))
        self.assertContains(r, 'ثبت سند جدید')
        self.assertContains(r, self.bank.title)

    def test_create_answers_204_with_toast_event(self):
        r = self.client.post(reverse('main:acc_p_voucher_new', args=[self.year.id]), self.data())
        self.assertEqual(r.status_code, 204)
        self.assertIn('accDone', trigger(r))
        self.assertEqual(Voucher.objects.filter(fiscal_year=self.year).count(), 1)

    def test_invalid_input_returns_the_form_with_the_error_and_keeps_the_rows(self):
        r = self.client.post(reverse('main:acc_p_voucher_new', args=[self.year.id]), self.data(debit='-5'))
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, 'role="alert"', status_code=400)
        self.assertContains(r, 'عوارض', status_code=400)
        self.assertFalse(Voucher.objects.exists())

    def test_bad_date_is_rejected(self):
        r = self.client.post(reverse('main:acc_p_voucher_new', args=[self.year.id]), self.data(date='1404/13/40'))
        self.assertEqual(r.status_code, 400)

    def test_closed_year_refuses_new_voucher(self):
        self.year.is_closed = True
        self.year.save()
        r = self.client.post(reverse('main:acc_p_voucher_new', args=[self.year.id]), self.data())
        self.assertEqual(r.status_code, 409)
        self.assertFalse(Voucher.objects.exists())

    def test_edit_temporary_voucher_but_not_a_final_one(self):
        v = self.voucher()
        url = reverse('main:acc_p_voucher_edit', args=[v.id])
        self.assertContains(self.client.get(url), 'ویرایش سند')
        self.assertEqual(self.client.post(url, self.data(credit='1000', description='ویرایش‌شده')).status_code, 204)
        v.refresh_from_db()
        self.assertEqual(v.description, 'ویرایش‌شده')
        ledger.finalize(self.dehyar, v)
        self.assertEqual(self.client.get(url).status_code, 409)
        self.assertEqual(self.client.post(url, self.data()).status_code, 409)

    def test_detail_shows_lines_and_actions(self):
        v = self.voucher()
        r = self.client.get(reverse('main:acc_p_voucher_detail', args=[v.id]))
        self.assertContains(r, 'قطعی کردن')
        self.assertContains(r, self.tax.title)

    def test_finalize_revert_delete(self):
        v = self.voucher()
        act = lambda a: self.client.post(reverse('main:acc_p_voucher_action', args=[v.id, a]))
        r = act('finalize')
        self.assertEqual(r.status_code, 204)
        self.assertIn('accDone', trigger(r))
        v.refresh_from_db()
        self.assertEqual(v.status, 'final')
        self.assertEqual(act('delete').status_code, 409)  # final vouchers cannot be deleted; error is a toast
        self.assertIn('accError', trigger(act('delete')))
        self.assertEqual(act('revert').status_code, 204)
        self.assertEqual(act('delete').status_code, 204)
        v.refresh_from_db()
        self.assertIsNotNone(v.deleted_at)

    def test_unbalanced_voucher_cannot_be_finalized(self):
        v = ledger.create_voucher(self.dehyar, self.year, self.d, 'general', 'x', [{'account': self.bank, 'debit': 5, 'credit': 0}])
        r = self.client.post(reverse('main:acc_p_voucher_action', args=[v.id, 'finalize']))
        self.assertEqual(r.status_code, 409)
        v.refresh_from_db()
        self.assertEqual(v.status, 'temporary')


class BillModalTests(PanelBase):
    def issue(self, **over):
        data = {'date': '1404/02/11', 'party': self.party.id, 'income_account': self.tax.id, 'amount': '۱٬۵۰۰',
                'description': 'عوارض', **over}
        return self.client.post(reverse('main:acc_p_bill_new', args=[self.year.id]), data)

    def test_issue_bill(self):
        r = self.issue()
        self.assertEqual(r.status_code, 204)
        self.assertIn('فیش شماره 1', trigger(r)['accDone']['message'])
        self.assertEqual(Bill.objects.get().amount, 1500)

    def test_issue_validation(self):
        for bad in ({'amount': '0'}, {'amount': '-3'}, {'amount': ''}, {'party': ''}, {'description': ''}, {'date': 'x'}):
            r = self.issue(**bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertContains(r, 'role="alert"', status_code=400)
        self.assertFalse(Bill.objects.exists())

    def test_party_of_another_municipality_is_refused(self):
        other = make_user('dehyari')
        foreign = Party.objects.create(municipality=make_municipality(other, village='روستای دیگر'), name='غریبه')
        self.assertEqual(self.issue(party=foreign.id).status_code, 400)
        self.assertFalse(Bill.objects.exists())

    def test_detail_prefills_the_remaining_amount(self):
        b = self.bill(5000)
        bills.record_payment(self.dehyar, b, self.d, 2000, self.bank, 'cash')
        self.assertContains(self.client.get(reverse('main:acc_p_bill_detail', args=[b.id])), 'value="3000"')

    def pay(self, b, amount):
        return self.client.post(reverse('main:acc_p_bill_pay', args=[b.id]), {
            'date': '1404/02/11', 'amount': amount, 'method': 'cash', 'bank_account': self.bank.id, 'reference': ''})

    def test_pay_posts_a_temporary_income_voucher(self):
        b = self.bill(1000)
        r = self.pay(b, '400')
        self.assertEqual(r.status_code, 204)
        pay = BillPayment.objects.get()
        self.assertEqual((pay.amount, pay.voucher.status, pay.voucher.kind), (400, 'temporary', 'income'))

    def test_overpayment_and_bad_amounts_are_refused_with_the_form(self):
        b = self.bill(1000)
        for bad, code in (('1001', 409), ('0', 400), ('-1', 400), ('abc', 400)):
            r = self.pay(b, bad)
            self.assertEqual(r.status_code, code, bad)
            self.assertContains(r, 'role="alert"', status_code=code)
        self.assertFalse(BillPayment.objects.exists())

    def test_cancel_payment_then_bill(self):
        b = self.bill(1000)
        self.pay(b, '1000')
        pay = BillPayment.objects.get()
        refused = self.client.post(reverse('main:acc_p_bill_cancel', args=[b.id]))
        self.assertEqual(refused.status_code, 409)  # still has a payment
        self.assertIn('accError', trigger(refused))
        self.assertEqual(self.client.post(reverse('main:acc_p_payment_cancel', args=[pay.id])).status_code, 204)
        self.assertFalse(BillPayment.objects.exists())
        self.assertEqual(self.client.post(reverse('main:acc_p_bill_cancel', args=[b.id])).status_code, 204)
        b.refresh_from_db()
        self.assertIsNotNone(b.canceled_at)
        self.assertEqual(self.pay(b, '10').status_code, 409)  # canceled bill takes no payment

    def test_final_payment_voucher_blocks_cancel_payment(self):
        b = self.bill(1000)
        self.pay(b, '500')
        pay = BillPayment.objects.get()
        ledger.finalize(self.dehyar, pay.voucher)
        r = self.client.post(reverse('main:acc_p_payment_cancel', args=[pay.id]))
        self.assertEqual(r.status_code, 409)
        self.assertTrue(BillPayment.objects.exists())


class BudgetModalTests(PanelBase):
    def test_set_budget_and_replace_it(self):
        url = reverse('main:acc_p_budget', args=[self.year.id])
        self.assertContains(self.client.get(url), self.tax.title)
        self.assertEqual(self.client.post(url, {'account': self.tax.id, 'amount': '۵٬۰۰۰'}).status_code, 204)
        self.assertEqual(self.client.post(url, {'account': self.tax.id, 'amount': '7000'}).status_code, 204)
        rows, _ = budget.report(self.dehyar, self.year)
        self.assertEqual([r['budget'] for r in rows], [7000])

    def test_validation(self):
        url = reverse('main:acc_p_budget', args=[self.year.id])
        for data in ({'account': '', 'amount': '5'}, {'account': self.bank.id, 'amount': '5'},
                     {'account': self.tax.id, 'amount': '-5'}, {'account': self.tax.id, 'amount': 'x'}):
            r = self.client.post(url, data)
            self.assertEqual(r.status_code, 400, data)
            self.assertContains(r, 'role="alert"', status_code=400)


class SetupTabTests(PanelBase):
    def test_open_year_and_seed_from_the_panel(self):
        other = make_user('dehyari')
        muni = make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        r = c.post(reverse('main:acc_p_seed'))
        self.assertEqual(r.status_code, 204)
        self.assertTrue(Account.objects.filter(municipality=muni).exists())
        r = c.post(reverse('main:acc_p_year_open'), {'year': '۱۴۰۵'})
        self.assertEqual(r.status_code, 204)
        self.assertTrue(muni.fiscal_years.filter(year=1405).exists())
        again = c.post(reverse('main:acc_p_year_open'), {'year': '1405'})
        self.assertEqual(again.status_code, 409)
        self.assertIn('accError', trigger(again))
        self.assertEqual(c.post(reverse('main:acc_p_year_open'), {'year': 'x'}).status_code, 400)

    def test_setup_actions_need_post_and_the_right_role(self):
        self.assertEqual(self.client.get(reverse('main:acc_p_seed')).status_code, 405)
        self.assertEqual(client_for(make_user('citizen')).post(reverse('main:acc_p_year_open'), {'year': '1405'}).status_code, 302)


class ListTabTests(PanelBase):
    def tab(self, tab, **params):
        return self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': tab, **params})

    def test_trial_and_ledger_modal(self):
        self.voucher(), self.voucher(status='final')
        r = self.tab('trial')
        self.assertEqual(r.context['totals']['debit'], 2000)
        self.assertEqual(self.tab('trial', final=1).context['totals']['debit'], 1000)
        self.assertContains(r, reverse('main:acc_p_ledger', args=[self.year.id, self.bank.id]))
        led = self.client.get(reverse('main:acc_p_ledger', args=[self.year.id, self.bank.id]))
        self.assertEqual(len(led.context['rows']), 2)

    def test_parties_tab_search_and_modal_create(self):
        self.assertContains(self.tab('parties', q='رضایی'), 'علی رضایی')
        self.assertNotContains(self.tab('parties', q='نامعلوم'), 'علی رضایی')
        url = reverse('main:acc_p_party_new')
        self.assertContains(self.client.get(url), 'طرف حساب جدید')
        ok = self.client.post(url, {'kind': 'real', 'name': 'زهرا احمدی', 'national_id': '۰۰۱۲۳۴۵۶۷۹'})
        self.assertEqual(ok.status_code, 204)
        self.assertTrue(Party.objects.filter(municipality=self.muni, name='زهرا احمدی', national_id='0012345679').exists())
        for bad in ({'name': ''}, {'name': 'x', 'national_id': '123'}, {'name': 'x', 'kind': 'zzz'}):
            r = self.client.post(url, {'kind': 'real', **bad})
            self.assertEqual(r.status_code, 400, bad)
            self.assertContains(r, 'role="alert"', status_code=400)

    def test_accounts_tab_and_modal_create(self):
        self.assertContains(self.tab('accounts', q=self.tax.title[:6]), self.tax.title)
        url = reverse('main:acc_p_account_new')
        self.assertContains(self.client.get(url), 'حساب جدید')
        data = {'code': 'X100', 'title': 'حساب آزمون', 'kind': 'asset', 'nature': 'debit', 'is_postable': 'on'}
        self.assertEqual(self.client.post(url, data).status_code, 204)
        self.assertEqual(self.client.post(url, data).status_code, 409)  # duplicate code
        self.assertEqual(self.client.post(url, {**data, 'code': 'ک ۱'}).status_code, 400)

    def test_other_municipality_cannot_see_these_rows(self):
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        self.assertNotContains(c.get(reverse('main:acc_panel'), {'tab': 'parties'}), 'علی رضایی')
        self.assertNotContains(c.get(reverse('main:acc_panel'), {'tab': 'accounts'}), self.tax.title)
        self.assertEqual(c.get(reverse('main:acc_p_ledger', args=[self.year.id, self.bank.id])).status_code, 404)
