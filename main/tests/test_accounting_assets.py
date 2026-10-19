"""Fixed assets: schedules, the yearly depreciation voucher and disposal."""
from datetime import date

from django.urls import reverse

from main.accounting import assets, ledger
from main.models import Account, Asset, AssetDepreciation, Voucher
from main.office.errors import Conflict, Invalid
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase

START = date(2025, 6, 22)                    # 1404/04/01


class AssetBase(LedgerBase):
    def setUp(self):
        super().setUp()
        self.fixed = Account.objects.create(municipality=self.muni, code='211', title='دارایی‌های ثابت', kind='asset', nature='debit')
        self.accum = Account.objects.create(municipality=self.muni, code='212', title='استهلاک انباشته', kind='asset', nature='credit')
        self.year2 = ledger.open_year(self.dehyar, 1405)

    def asset(self, **kw):
        data = dict(code='A1', title='خودرو', acquisition_date=START, cost=12_000_000, salvage=0, life_years=4, method='line',
                    account=self.fixed, accumulated_account=self.accum, expense_account=self.salary)
        data.update(kw)
        return assets.create_asset(self.dehyar, **data)


class ScheduleTests(AssetBase):
    def test_straight_line_prorates_the_first_year_and_ends_at_the_salvage_value(self):
        plan = assets.schedule(self.asset())
        self.assertEqual(plan, {1404: 2_250_000, 1405: 3_000_000, 1406: 3_000_000, 1407: 3_000_000, 1408: 750_000})
        self.assertEqual(sum(plan.values()), 12_000_000)

    def test_salvage_value_stays_on_the_books(self):
        plan = assets.schedule(self.asset(code='A2', salvage=2_000_000, acquisition_date=date(2025, 3, 21)))
        self.assertEqual(sum(plan.values()), 10_000_000)
        self.assertEqual(plan[1404], 2_500_000)

    def test_declining_balance_never_goes_below_the_salvage_value(self):
        asset = self.asset(code='A3', cost=10_000_000, salvage=1_000_000, life_years=5, method='declining',
                           acquisition_date=date(2025, 3, 21))
        plan = assets.schedule(asset)
        self.assertEqual(list(plan.values()), [4_000_000, 2_400_000, 1_440_000, 864_000, 296_000])
        self.assertEqual(sum(plan.values()), 9_000_000)

    def test_a_disposed_asset_stops_at_the_disposal_month(self):
        asset = self.asset()
        asset.disposed_on = date(2026, 6, 5)                                        # 1405/03/15
        plan = assets.schedule(asset)
        self.assertEqual(plan, {1404: 2_250_000, 1405: 750_000})

    def test_amounts_are_whole_rials(self):
        plan = assets.schedule(self.asset(code='A4', cost=1_000_000, life_years=3, acquisition_date=date(2025, 5, 22)))
        self.assertTrue(all(v == v.to_integral_value() for v in plan.values()))
        self.assertEqual(sum(plan.values()), 1_000_000)


class RegisterTests(AssetBase):
    def test_validation(self):
        for kw in ({'cost': 0}, {'salvage': 12_000_000}, {'life_years': 0}, {'life_years': 101}, {'method': 'x'}, {'title': ''}):
            with self.subTest(kw=kw), self.assertRaises(Invalid):
                self.asset(code=f'X{len(kw)}{list(kw)[0]}', **kw)
        with self.assertRaises(Invalid):
            self.asset(code='B1', account=self.salary)                               # a budget account is not an asset account
        with self.assertRaises(Invalid):
            self.asset(code='B2', expense_account=self.bank)                         # the expense account must be a use account

    def test_code_is_unique_per_municipality(self):
        self.asset()
        with self.assertRaises(Conflict):
            self.asset()

    def test_accounts_of_another_municipality_are_refused(self):
        from main.tests.helpers import make_municipality
        from main.tests.test_accounting_ledger import make_user
        other = make_user('dehyari')
        other_muni = make_municipality(other)
        foreign = Account.objects.create(municipality=other_muni, code='211', title='x', kind='asset', nature='debit')
        with self.assertRaises(Invalid):
            self.asset(account=foreign)

    def test_default_accounts_are_created_once(self):
        a, b, c = assets.ensure_accounts(self.dehyar)
        again = assets.ensure_accounts(self.dehyar)
        self.assertEqual((a.code, b.code, c.kind), ('211', '212', 'budget_use'))
        self.assertEqual((a.pk, b.pk, c.pk), tuple(x.pk for x in again))

    def test_only_an_untouched_asset_can_be_deleted(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        with self.assertRaises(Conflict):
            assets.delete_asset(self.dehyar, asset)
        fresh = self.asset(code='A9')
        assets.delete_asset(self.dehyar, fresh)
        self.assertFalse(Asset.objects.filter(pk=fresh.pk).exists())


class DepreciationVoucherTests(AssetBase):
    def test_the_year_is_posted_as_one_temporary_voucher(self):
        self.asset()
        voucher = assets.post_year(self.dehyar, self.year)
        self.assertEqual((voucher.status, voucher.date), ('temporary', self.year.end_date))
        lines = {ln.account.code: (ln.debit, ln.credit) for ln in voucher.lines.all()}
        self.assertEqual(lines, {'6010101001': (2_250_000, 0), '212': (0, 2_250_000)})
        self.assertEqual(AssetDepreciation.objects.get().amount, 2_250_000)

    def test_posting_again_replaces_a_temporary_voucher_but_not_a_final_one(self):
        self.asset()
        first = assets.post_year(self.dehyar, self.year)
        second = assets.post_year(self.dehyar, self.year)
        first.refresh_from_db()
        self.assertIsNotNone(first.deleted_at)
        self.assertEqual(AssetDepreciation.objects.count(), 1)
        ledger.finalize(self.dehyar, second)
        with self.assertRaises(Conflict):
            assets.post_year(self.dehyar, self.year)

    def test_preview_warns_about_unposted_earlier_years(self):
        self.asset()
        rows, missing = assets.preview(self.dehyar, self.year2)
        self.assertEqual((rows[0]['amount'], missing), (3_000_000, ['A1']))
        assets.post_year(self.dehyar, self.year)
        rows, missing = assets.preview(self.dehyar, self.year2)
        self.assertEqual((rows[0]['before'], rows[0]['after'], missing), (2_250_000, 5_250_000, []))

    def test_two_assets_share_the_accounts_in_one_voucher(self):
        self.asset()
        self.asset(code='A2', title='رایانه', cost=2_400_000, life_years=2, acquisition_date=date(2025, 3, 21))
        voucher = assets.post_year(self.dehyar, self.year)
        self.assertEqual(voucher.lines.count(), 2)
        self.assertEqual(AssetDepreciation.objects.count(), 2)
        self.assertEqual(ledger.is_balanced(voucher), True)

    def test_nothing_to_post_and_a_closed_year(self):
        with self.assertRaises(Conflict):
            assets.post_year(self.dehyar, self.year)
        self.asset()
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            assets.post_year(self.dehyar, self.year)


class DisposalTests(AssetBase):
    def test_a_sale_above_book_value_books_a_gain_and_the_depreciation_to_the_month(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        voucher = assets.dispose(self.dehyar, asset, date(2026, 6, 5), 10_000_000, self.bank, self.tax)
        lines = sorted((ln.account.code, ln.debit, ln.credit) for ln in voucher.lines.all())
        self.assertEqual(lines, sorted([
            ('6010101001', 750_000, 0), ('212', 0, 750_000),                           # 1405/01..03
            ('212', 3_000_000, 0), ('1120101', 10_000_000, 0), ('211', 0, 12_000_000), ('5010101001', 0, 1_000_000)]))
        self.assertTrue(ledger.is_balanced(voucher))
        asset.refresh_from_db()
        self.assertEqual((asset.status, asset.disposal_amount, asset.disposal_voucher), ('disposed', 10_000_000, voucher))
        self.assertEqual(assets.posted_total(asset), 3_000_000)

    def test_a_sale_below_book_value_books_a_loss(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        voucher = assets.dispose(self.dehyar, asset, date(2026, 6, 5), 5_000_000, self.bank, self.salary)
        by_account = {}
        for ln in voucher.lines.all():
            by_account.setdefault(ln.account.code, []).append((ln.debit, ln.credit))
        self.assertIn((4_000_000, 0), by_account['6010101001'])                     # the loss
        self.assertTrue(ledger.is_balanced(voucher))

    def test_scrapping_without_proceeds(self):
        asset = self.asset(code='A5', acquisition_date=date(2025, 3, 21), cost=1_000_000, life_years=1)
        assets.post_year(self.dehyar, self.year)
        voucher = assets.dispose(self.dehyar, asset, date(2026, 3, 1), 0)
        self.assertTrue(ledger.is_balanced(voucher))

    def test_earlier_years_must_be_posted_first(self):
        asset = self.asset()
        with self.assertRaises(Conflict):
            assets.dispose(self.dehyar, asset, date(2026, 6, 5), 0)
        asset.refresh_from_db()
        self.assertEqual((asset.status, asset.disposed_on), ('active', None))

    def test_a_result_account_is_needed_when_the_price_differs_from_book_value(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        with self.assertRaises(Invalid):
            assets.dispose(self.dehyar, asset, date(2026, 6, 5), 9_000_000 + 1, self.bank)
        self.assertTrue(assets.dispose(self.dehyar, asset, date(2026, 6, 5), 9_000_000, self.bank))      # exactly the book value

    def test_a_disposed_asset_cannot_be_disposed_again_and_is_not_depreciated_afterwards(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        assets.dispose(self.dehyar, asset, date(2026, 6, 5), 9_000_000, self.bank)
        with self.assertRaises(Conflict):
            assets.dispose(self.dehyar, asset, date(2026, 6, 6), 0)
        year3 = ledger.open_year(self.dehyar, 1406)
        self.assertEqual(assets.preview(self.dehyar, year3)[0], [])
        self.assertEqual(assets.preview(self.dehyar, self.year2)[0], [])           # its last depreciation is in the disposal voucher

    def test_a_year_with_a_disposal_can_still_be_reposted_without_touching_the_disposal(self):
        asset = self.asset()
        assets.post_year(self.dehyar, self.year)
        assets.dispose(self.dehyar, asset, date(2026, 6, 5), 9_000_000, self.bank)
        self.asset(code='A6', title='دیگر', cost=1_200_000, life_years=2, acquisition_date=date(2026, 3, 21))
        assets.post_year(self.dehyar, self.year2)
        self.assertEqual(AssetDepreciation.objects.filter(asset=asset).count(), 2)       # 1404 and the disposal-year share survive
        self.assertEqual(Voucher.objects.filter(deleted_at__isnull=True).count(), 3)


class PanelTests(AssetBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_tab_form_create_depreciate_dispose(self):
        page = self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'assets'})
        self.assertContains(page, 'دارایی جدید')
        self.assertEqual(self.client.get(reverse('main:acc_p_asset_new')).status_code, 200)
        done = self.client.post(reverse('main:acc_p_asset_new'), {
            'code': 'P1', 'title': 'تراکتور', 'acquisition_date': '1404/04/01', 'cost': '12,000,000', 'salvage': '0', 'life_years': '4',
            'method': 'line', 'account': self.fixed.id, 'accumulated_account': self.accum.id, 'expense_account': self.salary.id})
        self.assertEqual(done.status_code, 204)
        asset = Asset.objects.get(code='P1')
        bad = self.client.post(reverse('main:acc_p_asset_new'), {'code': 'P2'})
        self.assertEqual(bad.status_code, 400)
        tab = self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'assets'})
        self.assertEqual(tab.context['dep_total'], 2_250_000)
        post = self.client.post(reverse('main:acc_p_asset_depreciate', args=[self.year.id]))
        self.assertEqual(post.status_code, 204)
        self.assertEqual(self.client.get(reverse('main:acc_p_asset_dispose', args=[asset.id])).status_code, 200)
        gone = self.client.post(reverse('main:acc_p_asset_dispose', args=[asset.id]), {
            'date': '1405/03/15', 'proceeds': '9000000', 'proceeds_account': self.bank.id})
        self.assertEqual(gone.status_code, 204)
        asset.refresh_from_db()
        self.assertEqual(asset.status, 'disposed')
        again = self.client.post(reverse('main:acc_p_asset_depreciate', args=[self.year2.id]))
        self.assertEqual(again.status_code, 409)          # nothing left to depreciate in 1405: it went out in the disposal voucher

    def test_accounts_endpoint_and_delete(self):
        self.assertEqual(self.client.post(reverse('main:acc_p_asset_accounts')).status_code, 204)
        self.assertTrue(Account.objects.filter(municipality=self.muni, code='6010401001').exists())
        asset = self.asset()
        self.assertEqual(self.client.post(reverse('main:acc_p_asset_delete', args=[asset.id])).status_code, 204)
        self.assertEqual(self.client.get(reverse('main:acc_p_asset_new')).context['asset_accounts'].count() >= 2, True)
