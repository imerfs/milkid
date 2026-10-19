"""Production series and expiry dates: lots in the stock log, first-expiry-first-out sales, purchase profit and the screens."""
from datetime import date

from django.urls import reverse

from main.accounting.trade import inventory, invoices, production, stockdocs
from main.models import Product
from main.tests.helpers import client_for
from main.tests.test_trade import TradeBase

D1, D2, D3 = date(2025, 4, 1), date(2025, 4, 10), date(2025, 5, 1)
SOON, LATER = date(2025, 6, 1), date(2025, 12, 1)


def u(name, *args):
    return reverse(f'main:{name}', args=args)


class LotTests(TradeBase):
    def receive_lot(self, product, qty, lot, expiry, on=D1, cost=100):
        return stockdocs.create_doc(self.dehyar, self.year, 'receipt', on, self.wh,
                                    [{'product': product, 'qty': qty, 'unit_cost': cost, 'lot': lot, 'expiry': expiry}])

    def lots(self, product):
        return {(lot, expiry): q for (_, _, lot, expiry), q in inventory.lot_balances(self.muni, product).items()}

    def test_sales_take_the_soonest_expiry_first(self):
        self.receive_lot(self.rice, 10, 'B-LATE', LATER)
        self.receive_lot(self.rice, 10, 'A-SOON', SOON)
        self.sale(self.rice, 12, 300, D3)
        self.assertEqual(self.lots(self.rice), {('B-LATE', LATER): 8})
        self.assertEqual(self.stock(self.rice), 8)

    def test_expired_series_are_sold_last(self):
        self.receive_lot(self.rice, 10, 'OLD', date(2025, 4, 20))
        self.receive_lot(self.rice, 10, 'NEW', LATER)
        self.sale(self.rice, 5, 300, D3)                 # OLD expired on the sale date, NEW goes first
        self.assertEqual(self.lots(self.rice), {('OLD', date(2025, 4, 20)): 10, ('NEW', LATER): 5})

    def test_untracked_stock_goes_after_the_series(self):
        self.receive(self.rice, 10, 100)
        self.receive_lot(self.rice, 5, 'A', SOON)
        self.sale(self.rice, 7, 300, D3)
        self.assertEqual(self.lots(self.rice), {('', None): 8})      # the 5 in the series went first, then 2 of the untracked 10

    def test_cancelling_a_sale_puts_the_series_back(self):
        self.receive_lot(self.rice, 10, 'A', SOON)
        inv = self.sale(self.rice, 4, 300, D3)
        invoices.cancel_invoice(self.dehyar, inv)
        self.assertEqual(self.lots(self.rice), {('A', SOON): 10})

    def test_transfer_keeps_the_series(self):
        self.receive_lot(self.rice, 10, 'A', SOON)
        stockdocs.create_doc(self.dehyar, self.year, 'transfer', D2, self.wh, [{'product': self.rice, 'qty': 4}], to_warehouse=self.main)
        by_wh = {(wid, lot): q for (_, wid, lot, _), q in inventory.lot_balances(self.muni, self.rice).items()}
        self.assertEqual(by_wh, {(self.wh.id, 'A'): 6, (self.main.id, 'A'): 4})

    def test_purchase_invoice_records_series_and_expiry(self):
        invoices.create_invoice(self.dehyar, self.year, 'purchase', D1, self.supplier,
                                [{'product': self.rice, 'qty': 20, 'unit_price': 100, 'lot': 'P-7', 'expiry': LATER}])
        self.assertEqual(self.lots(self.rice), {('P-7', LATER): 20})

    def test_production_run_takes_a_series_and_expiry(self):
        bread = inventory.create_product(self.dehyar, code='M2', name='نان', sell_price=50)
        self.receive(self.rice, 100, 100)
        formula = production.create_formula(self.dehyar, bread, 10, [{'product': self.rice, 'qty': 5}])
        run = production.run_production(self.dehyar, self.year, formula, 2, D2, expiry=LATER)
        self.assertEqual(run.lot, f'{self.year.year}-{run.number}')
        self.assertEqual(self.lots(bread), {(run.lot, LATER): 20})
        named = production.run_production(self.dehyar, self.year, formula, 1, D2, lot='S-9')
        self.assertEqual(named.lot, 'S-9')

    def test_report_flags_expired_and_expiring_series(self):
        self.receive_lot(self.rice, 5, 'GONE', date(2025, 4, 5))
        self.receive_lot(self.rice, 5, 'SOON', date(2025, 5, 10))
        self.receive_lot(self.rice, 5, 'OK', LATER)
        rows = {r['lot']: r['state'] for r in inventory.lot_report(self.dehyar, today=date(2025, 5, 1))}
        self.assertEqual(rows, {'GONE': 'expired', 'SOON': 'soon', 'OK': None})

    def test_update_prices_after_a_purchase(self):
        inventory.update_prices(self.dehyar, [(self.rice, 120, 180), (self.oil, 0, 0)])
        self.rice.refresh_from_db()
        self.assertEqual((self.rice.buy_price, self.rice.sell_price), (120, 180))


class LotViewTests(TradeBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_purchase_form_has_profit_series_and_expiry_columns(self):
        page = self.client.get(u('acc_p_trade_invoice_new', self.year.id, 'purchase'))
        for needle in ('درصد سود', 'سری ساخت', 'تاریخ انقضا', 'data-trade-margin', 'update_prices'):
            self.assertContains(page, needle)
        self.assertNotContains(self.client.get(u('acc_p_trade_invoice_new', self.year.id, 'sale')), 'data-trade-margin')

    def test_purchase_posts_series_expiry_and_updates_prices(self):
        response = self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'purchase'), {
            'on': '1404/02/11', 'party': self.supplier.id, 'warehouse': self.wh.id, 'update_prices': 'on', 'product': [self.rice.id],
            'qty': ['10'], 'unit_price': ['۱٬۰۰۰'], 'margin': ['20'], 'sell_price': ['۱٬۲۰۰'], 'lot': ['L-5'], 'expiry': ['1405/01/01'],
            'discount': ['']})
        self.assertEqual(response.status_code, 204, response.headers.get('HX-Trigger'))
        lots = inventory.lot_balances(self.muni, self.rice)
        self.assertEqual({(lot, expiry) for (_, _, lot, expiry) in lots}, {('L-5', date(2026, 3, 21))})
        product = Product.objects.get(pk=self.rice.pk)
        self.assertEqual((product.buy_price, product.sell_price), (1000, 1200))

    def test_bad_expiry_date_comes_back_to_the_form(self):
        response = self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'purchase'), {
            'on': '1404/02/11', 'party': self.supplier.id, 'warehouse': self.wh.id, 'product': [self.rice.id], 'qty': ['1'],
            'unit_price': ['100'], 'expiry': ['not a date']})
        self.assertGreaterEqual(response.status_code, 400)

    def test_receipt_form_and_production_modal_take_series(self):
        self.assertContains(self.client.get(u('acc_p_trade_doc_new', self.year.id, 'receipt')), 'تاریخ انقضا')
        bread = inventory.create_product(self.dehyar, code='M2', name='نان', sell_price=50)
        self.receive(self.rice, 100, 100)
        formula = production.create_formula(self.dehyar, bread, 10, [{'product': self.rice, 'qty': 5}])
        self.assertContains(self.client.get(u('acc_p_trade_run_new', self.year.id, formula.id)), 'pr-lot')
        run = self.client.post(u('acc_p_trade_run_new', self.year.id, formula.id),
                               {'date': '1404/02/11', 'batches': '1', 'warehouse': self.wh.id, 'lot': 'S-1', 'expiry': '1405/02/11'})
        self.assertEqual(run.status_code, 204, run.headers.get('HX-Trigger'))
        self.assertEqual({lot for (_, _, lot, _) in inventory.lot_balances(self.muni, bread)}, {'S-1'})

    def test_pos_lists_stock_and_nearest_expiry_and_stock_tab_lists_series(self):
        stockdocs.create_doc(self.dehyar, self.year, 'receipt', D1, self.wh,
                             [{'product': self.rice, 'qty': 10, 'unit_cost': 100, 'lot': 'A', 'expiry': date.today()}])
        pos = self.client.get(u('acc_panel'), {'tab': 'trade_pos', 'year': self.year.id})
        self.assertContains(pos, 'data-pos-grid')
        self.assertContains(pos, '"expiry"')
        stock = self.client.get(u('acc_panel'), {'tab': 'trade_stock', 'year': self.year.id})
        self.assertContains(stock, 'سری ساخت و تاریخ انقضا')
