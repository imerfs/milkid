"""Accounting pages: access control, voucher entry through the form, Persian input, reports."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.accounting import ledger
from main.accounting.chart import seed_default_accounts
from main.accounting.parse import parse_amount, parse_jalali
from main.models import Account, Party, Voucher
from main.office.errors import Invalid
from main.tests.helpers import client_for, make_municipality, make_user as _make_user


def make_user(*args, **kwargs):
    return User.objects.get(pk=_make_user(*args, **kwargs).pk)


class ParseTests(TestCase):
    def test_persian_and_arabic_digits_and_separators(self):
        self.assertEqual(parse_amount('۱٬۲۳۴٬۵۶۷'), 1234567)
        self.assertEqual(parse_amount('١٢٣,٤٥'), 12345)
        self.assertEqual(parse_amount(''), 0)

    def test_bad_amounts(self):
        for bad in ('12.5', '-3', 'abc', '1e5'):
            with self.assertRaises(Invalid):
                parse_amount(bad)

    def test_jalali_date(self):
        self.assertEqual(parse_jalali('۱۴۰۴/۰۲/۱۱'), date(2025, 5, 1))
        self.assertEqual(parse_jalali('1404-02-11'), date(2025, 5, 1))

    def test_bad_dates(self):
        for bad in ('', '1404/13/01', '1404/02/32', 'x', '1404/02'):
            with self.assertRaises(Invalid):
                parse_jalali(bad)


class AccountingPagesBase(TestCase):
    def setUp(self):
        self.dehyar = make_user('dehyari')
        self.muni = make_municipality(self.dehyar)
        self.client = client_for(self.dehyar)
        self.year = ledger.open_year(self.dehyar, 1404)
        seed_default_accounts(self.dehyar)
        self.bank = Account.objects.get(municipality=self.muni, code='1120101')
        self.tax = Account.objects.get(municipality=self.muni, code='5010101001')

    def post_voucher(self, debit='1000', credit='1000', url=None, client=None, **extra):
        data = {'date': '1404/02/11', 'kind': 'income', 'description': 'عوارض',
                'account': [self.bank.id, self.tax.id], 'party': ['', ''], 'cost_center': ['', ''],
                'line_description': ['', ''], 'debit': [debit, ''], 'credit': ['', credit], **extra}
        return (client or self.client).post(url or reverse('main:acc_voucher_new', args=[self.year.id]), data)


class AccessTests(AccountingPagesBase):
    def test_anonymous_goes_to_login(self):
        r = client_for().get(reverse('main:acc_home'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)

    def test_citizen_is_turned_away(self):
        r = client_for(make_user('citizen')).get(reverse('main:acc_home'))
        self.assertRedirects(r, reverse('main:dashboard'), fetch_redirect_response=False)

    def test_accountant_of_the_village_can_open(self):
        acc = make_user('accountant', city_village=self.muni.city_village)
        self.assertEqual(client_for(acc).get(reverse('main:acc_home')).status_code, 200)

    def test_other_municipality_gets_404_on_everything(self):
        other = make_user('dehyari')
        make_municipality(other, village='روستای دیگر')
        c = client_for(other)
        v = ledger.create_voucher(self.dehyar, self.year, date(2025, 5, 1), 'general', 'x',
                                  [{'account': self.bank, 'debit': 5, 'credit': 0}])
        for name, args in [('acc_vouchers', [self.year.id]), ('acc_voucher_new', [self.year.id]),
                           ('acc_voucher_detail', [v.id]), ('acc_voucher_edit', [v.id]),
                           ('acc_trial', [self.year.id]), ('acc_ledger', [self.year.id, self.bank.id])]:
            self.assertEqual(c.get(reverse(f'main:{name}', args=args)).status_code, 404, name)
        for name in ('acc_voucher_finalize', 'acc_voucher_delete', 'acc_voucher_revert'):
            self.assertEqual(c.post(reverse(f'main:{name}', args=[v.id])).status_code, 404, name)
        v.refresh_from_db()
        self.assertEqual((v.status, v.deleted_at), ('temporary', None))

    def test_state_changes_need_post(self):
        v = ledger.create_voucher(self.dehyar, self.year, date(2025, 5, 1), 'general', 'x',
                                  [{'account': self.bank, 'debit': 5, 'credit': 0}])
        self.assertEqual(self.client.get(reverse('main:acc_voucher_delete', args=[v.id])).status_code, 405)


class HomeAndSeedTests(AccountingPagesBase):
    def test_home_lists_the_year_and_opening_twice_shows_error(self):
        self.assertContains(self.client.get(reverse('main:acc_home')), '۱۴۰۴')
        r = self.client.post(reverse('main:acc_home'), {'year': '1404'})
        self.assertEqual(r.status_code, 409)

    def test_open_year_with_persian_digits(self):
        self.client.post(reverse('main:acc_home'), {'year': '۱۴۰۵'})
        self.assertTrue(self.muni.fiscal_years.filter(year=1405).exists())

    def test_seed_is_idempotent_and_has_the_budget_groups(self):
        before = Account.objects.filter(municipality=self.muni).count()
        seed_default_accounts(self.dehyar)
        self.assertEqual(Account.objects.filter(municipality=self.muni).count(), before)
        for code in ('501', '502', '503', '601', '602', '603', '112', '311'):
            self.assertTrue(Account.objects.filter(municipality=self.muni, code=code, is_postable=False).exists()
                            or Account.objects.filter(municipality=self.muni, code=code).exists(), code)
        self.assertFalse(Account.objects.get(municipality=self.muni, code='501').is_postable)


class VoucherFormTests(AccountingPagesBase):
    def test_create_balanced_voucher_via_form(self):
        r = self.post_voucher('۱٬۰۰۰', '۱۰۰۰')
        v = Voucher.objects.get()
        self.assertRedirects(r, reverse('main:acc_voucher_detail', args=[v.id]))
        self.assertEqual((v.number, v.date, v.lines.count()), (1, date(2025, 5, 1), 2))

    def test_unbalanced_voucher_saves_but_shows_the_badge_and_cannot_be_finalized(self):
        self.post_voucher('1000', '900')
        v = Voucher.objects.get()
        page = self.client.get(reverse('main:acc_voucher_detail', args=[v.id]))
        self.assertContains(page, 'بی‌حساب')
        r = self.client.post(reverse('main:acc_voucher_finalize', args=[v.id]), follow=True)
        v.refresh_from_db()
        self.assertEqual(v.status, 'temporary')
        self.assertContains(r, 'بی‌حساب')

    def test_bad_input_rerenders_with_error_and_keeps_text(self):
        r = self.post_voucher('-5', '1000', description='متن فارسی من')
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, 'متن فارسی من', status_code=400)
        self.assertEqual(Voucher.objects.count(), 0)

    def test_foreign_account_id_in_post_is_rejected(self):
        other = make_user('dehyari')
        om = make_municipality(other, village='روستای دیگر')
        foreign = Account.objects.create(municipality=om, code='1', title='x', kind='asset', nature='debit')
        r = self.client.post(reverse('main:acc_voucher_new', args=[self.year.id]), {
            'date': '1404/02/11', 'kind': 'general', 'description': 'x', 'account': [foreign.id],
            'party': [''], 'cost_center': [''], 'line_description': [''], 'debit': ['5'], 'credit': ['']})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Voucher.objects.count(), 0)

    def test_blank_rows_are_ignored(self):
        r = self.client.post(reverse('main:acc_voucher_new', args=[self.year.id]), {
            'date': '1404/02/11', 'kind': 'general', 'description': 'x',
            'account': [self.bank.id, '', self.tax.id], 'party': ['', '', ''], 'cost_center': ['', '', ''],
            'line_description': ['', '', ''], 'debit': ['5', '', ''], 'credit': ['', '', '5']})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Voucher.objects.get().lines.count(), 2)

    def test_edit_finalize_revert_delete_flow(self):
        self.post_voucher()
        v = Voucher.objects.get()
        edit = reverse('main:acc_voucher_edit', args=[v.id])
        self.assertContains(self.client.get(edit), 'عوارض')
        self.post_voucher('7', '7', url=edit, description='ویرایش‌شده')
        v.refresh_from_db()
        self.assertEqual(v.description, 'ویرایش‌شده')
        self.client.post(reverse('main:acc_voucher_finalize', args=[v.id]))
        v.refresh_from_db()
        self.assertEqual(v.status, 'final')
        self.assertEqual(self.client.get(edit).status_code, 409)          # final: locked
        self.client.post(reverse('main:acc_voucher_delete', args=[v.id]))
        self.assertIsNone(Voucher.objects.get().deleted_at)               # still there
        self.client.post(reverse('main:acc_voucher_revert', args=[v.id]))
        self.client.post(reverse('main:acc_voucher_delete', args=[v.id]))
        self.assertIsNotNone(Voucher.objects.get().deleted_at)

    def test_accountant_cannot_revert(self):
        self.post_voucher()
        v = Voucher.objects.get()
        ledger.finalize(self.dehyar, v)
        acc = make_user('accountant', city_village=self.muni.city_village)
        client_for(acc).post(reverse('main:acc_voucher_revert', args=[v.id]))
        v.refresh_from_db()
        self.assertEqual(v.status, 'final')


class VoucherListTests(AccountingPagesBase):
    def test_filters(self):
        self.post_voucher()
        self.post_voucher(description='حقوق')
        url = reverse('main:acc_vouchers', args=[self.year.id])
        self.assertContains(self.client.get(url), 'حقوق')
        page = self.client.get(url, {'q': 'حقوق'})
        self.assertEqual(len(page.context['page'].object_list), 1)
        page = self.client.get(url, {'status': 'final'})
        self.assertEqual(len(page.context['page'].object_list), 0)
        page = self.client.get(url, {'number_from': '2', 'number_to': '2'})
        self.assertEqual(page.context['page'].object_list[0].number, 2)

    def test_garbage_filters_do_not_crash(self):
        url = reverse('main:acc_vouchers', args=[self.year.id])
        self.assertEqual(self.client.get(url, {'number_from': 'x', 'status': 'zzz', 'page': '999'}).status_code, 200)

    def test_empty_state(self):
        self.assertContains(self.client.get(reverse('main:acc_vouchers', args=[self.year.id])), 'سندی ثبت نشده')


class MasterDataTests(AccountingPagesBase):
    def test_add_account(self):
        r = self.client.post(reverse('main:acc_accounts'), {
            'code': '6010101009', 'title': 'تعمیرات', 'kind': 'budget_use', 'nature': 'debit', 'is_postable': 'on'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Account.objects.filter(municipality=self.muni, code='6010101009').exists())

    def test_duplicate_account_code_shows_error(self):
        r = self.client.post(reverse('main:acc_accounts'), {
            'code': '1120101', 'title': 'dup', 'kind': 'asset', 'nature': 'debit'})
        self.assertEqual(r.status_code, 409)

    def test_add_party_validates_national_id(self):
        url = reverse('main:acc_parties')
        bad = self.client.post(url, {'kind': 'real', 'name': 'علی', 'national_id': '0012345678'})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(url, {'kind': 'real', 'name': 'علی', 'national_id': '۰۰۱۲۳۴۵۶۷۹'})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(Party.objects.get().national_id, '0012345679')

    def test_lists_show_only_own_rows(self):
        other = make_user('dehyari')
        om = make_municipality(other, village='روستای دیگر')
        Party.objects.create(municipality=om, kind='real', name='غریبه', national_id='0012345679')
        self.assertNotContains(self.client.get(reverse('main:acc_parties')), 'غریبه')


class ReportPageTests(AccountingPagesBase):
    def test_trial_balance_and_ledger_pages(self):
        self.post_voucher('250', '250')
        page = self.client.get(reverse('main:acc_trial', args=[self.year.id]))
        self.assertContains(page, '۲۵۰')
        self.assertEqual(page.context['totals']['debit'], page.context['totals']['credit'])
        led = self.client.get(reverse('main:acc_ledger', args=[self.year.id, self.bank.id]))
        self.assertContains(led, '۲۵۰')

    def test_final_only_filter(self):
        self.post_voucher('250', '250')
        page = self.client.get(reverse('main:acc_trial', args=[self.year.id]), {'final': '1'})
        self.assertEqual(page.context['totals']['debit'], 0)


class DashboardLinkTests(AccountingPagesBase):
    def test_accountant_dashboard_stays_on_the_page_and_has_no_dead_links(self):
        html = self.client.get(reverse('main:accountant_dashboard')).content.decode()
        for tab in ('setup', 'vouchers', 'parties', 'bills', 'online', 'trial', 'budget', 'accounts'):
            self.assertIn(f'data-acc-tab="{tab}"', html)
        self.assertNotIn('href="#"', html)
        self.assertNotIn(f'href="{reverse("main:acc_home")}"', html)
