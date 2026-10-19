"""Trade: stock log and weighted-average valuation, invoices, stock documents, production, consignment, posting, profit."""
from datetime import date
from decimal import Decimal

from main.accounting import controls, ledger
from main.accounting.trade import consignment, inventory, invoices, posting, production, stockdocs
from main.models import Account, Invoice, Party, StockMove, TradeSettings, Voucher
from main.office.errors import Conflict, Invalid
from main.tests.helpers import make_municipality
from main.tests.test_accounting_ledger import LedgerBase, make_user

D1, D2, D3, D4 = date(2025, 4, 1), date(2025, 4, 10), date(2025, 5, 1), date(2025, 6, 1)


class TradeBase(LedgerBase):
    def setUp(self):
        super().setUp()
        self.customer = Party.objects.create(municipality=self.muni, name='مشتری الف')
        self.supplier = Party.objects.create(municipality=self.muni, name='تامین‌کننده')
        self.wh = inventory.default_warehouse(self.muni)
        self.main = inventory.create_warehouse(self.dehyar, code='2', name='انبار دوم')
        self.rice = inventory.create_product(self.dehyar, code='P1', name='برنج', unit='کیلو', buy_price=100, sell_price=150)
        self.oil = inventory.create_product(self.dehyar, code='P2', name='روغن', sell_price=900)

    def receive(self, product, qty, cost, on=D1, warehouse=None):
        return stockdocs.create_doc(self.dehyar, self.year, 'receipt', on, warehouse or self.wh,
                                    [{'product': product, 'qty': qty, 'unit_cost': cost}])

    def stock(self, product, warehouse=None):
        return inventory.stock_in(self.muni, product, warehouse or self.wh)

    def sale(self, product, qty, price, on=D3, **kw):
        return invoices.create_invoice(self.dehyar, self.year, 'sale', on, self.customer,
                                       [{'product': product, 'qty': qty, 'unit_price': price}], **kw)


class ValuationTests(TradeBase):
    def test_average_cost_follows_the_receipts_and_outflows_leave_at_the_average(self):
        self.receive(self.rice, 10, 100, D1)
        self.receive(self.rice, 10, 200, D2)
        value = inventory.valuation(self.muni, self.rice)
        self.assertEqual((value['qty'], value['avg'], value['value']), (20, 150, 3000))
        self.sale(self.rice, 5, 300)
        value = inventory.valuation(self.muni, self.rice)
        self.assertEqual((value['qty'], value['avg'], value['value']), (15, 150, 2250))

    def test_kardex_has_running_balances_and_filters(self):
        self.receive(self.rice, 10, 100, D1)
        self.sale(self.rice, 4, 300, D3)
        rows = inventory.kardex(self.dehyar, self.rice)
        self.assertEqual([(r['in'], r['out'], r['balance']) for r in rows], [(10, 0, 10), (0, 4, 6)])
        later = inventory.kardex(self.dehyar, self.rice, date_from=D2)
        self.assertEqual(len(later), 1)

    def test_stock_report_flags_a_shortage_and_values_stock(self):
        self.rice.min_stock = 20
        self.rice.save()
        self.receive(self.rice, 10, 100)
        rows = {r['product'].code: r for r in inventory.stock_report(self.dehyar)}
        self.assertEqual((rows['P1']['qty'], rows['P1']['value'], rows['P1']['low']), (10, 1000, True))
        self.assertEqual([r['product'].code for r in inventory.stock_report(self.dehyar, low_only=True)], ['P1'])
        self.assertFalse(rows['P2']['low'])

    def test_warehouses_are_kept_apart(self):
        self.receive(self.rice, 10, 100, D1, self.wh)
        self.receive(self.rice, 3, 100, D1, self.main)
        self.assertEqual((self.stock(self.rice), self.stock(self.rice, self.main)), (10, 3))
        row = inventory.stock_report(self.dehyar, warehouse=self.main)[0]
        self.assertEqual(row['qty'], 3)


class ProductTests(TradeBase):
    def test_codes_and_barcodes_are_unique_and_validated(self):
        with self.assertRaises(Conflict):
            inventory.create_product(self.dehyar, code='P1', name='دیگر')
        inventory.create_product(self.dehyar, code='P3', name='ج', barcode='123')
        with self.assertRaises(Conflict):
            inventory.create_product(self.dehyar, code='P4', name='د', barcode='123')
        for bad in ({'code': '', 'name': 'x'}, {'code': 'Z', 'name': ''}, {'code': 'Z', 'name': 'x', 'sell_price': -1}):
            with self.assertRaises(Invalid):
                inventory.create_product(self.dehyar, **bad)

    def test_an_opening_quantity_becomes_a_receipt(self):
        product = inventory.create_product(self.dehyar, code='P9', name='افتتاحی', opening_qty=7, opening_cost=50, opening_date=D1)
        self.assertEqual(self.stock(product), 7)
        self.assertEqual(inventory.valuation(self.muni, product)['avg'], 50)

    def test_a_product_with_history_cannot_be_deleted(self):
        self.receive(self.rice, 1, 1)
        with self.assertRaises(Conflict):
            inventory.delete_product(self.dehyar, self.rice)
        inventory.delete_product(self.dehyar, self.oil)

    def test_find_by_barcode_code_or_name(self):
        self.oil.barcode = '6260001'
        self.oil.save()
        self.assertEqual(inventory.find_product(self.dehyar, '6260001'), self.oil)
        self.assertEqual(inventory.find_product(self.dehyar, 'P1'), self.rice)
        self.assertEqual(inventory.find_product(self.dehyar, 'برن'), self.rice)
        self.assertIsNone(inventory.find_product(self.dehyar, 'نیست'))

    def test_other_municipalities_do_not_see_my_products(self):
        other = make_user('dehyari')
        make_municipality(other)
        self.assertEqual(list(inventory.products_for(other)), [])
        with self.assertRaises(Exception):
            inventory.get_product(other, self.rice.pk)


class StockDocTests(TradeBase):
    def test_issue_needs_stock_and_transfer_moves_between_warehouses_at_the_average(self):
        self.receive(self.rice, 10, 100)
        with self.assertRaises(Conflict):
            stockdocs.create_doc(self.dehyar, self.year, 'issue', D2, self.wh, [{'product': self.rice, 'qty': 11}])
        stockdocs.create_doc(self.dehyar, self.year, 'transfer', D2, self.wh, [{'product': self.rice, 'qty': 4}], to_warehouse=self.main)
        self.assertEqual((self.stock(self.rice), self.stock(self.rice, self.main)), (6, 4))
        self.assertEqual(inventory.valuation(self.muni, self.rice)['avg'], 100)
        with self.assertRaises(Invalid):
            stockdocs.create_doc(self.dehyar, self.year, 'transfer', D2, self.wh, [{'product': self.rice, 'qty': 1}], to_warehouse=self.wh)

    def test_adjustments_are_signed_and_stocktake_applies_the_difference(self):
        self.receive(self.rice, 10, 100)
        stockdocs.create_doc(self.dehyar, self.year, 'adjust', D2, self.wh, [{'product': self.rice, 'qty': -3}])
        self.assertEqual(self.stock(self.rice), 7)
        stockdocs.create_doc(self.dehyar, self.year, 'stocktake', D3, self.wh, [{'product': self.rice, 'counted': 9}])
        self.assertEqual(self.stock(self.rice), 9)
        doc = stockdocs.create_doc(self.dehyar, self.year, 'stocktake', D4, self.wh, [{'product': self.rice, 'counted': 9}])
        self.assertEqual(doc.moves.count(), 0)                                    # nothing differs: no movement

    def test_cancelling_a_receipt_that_later_sales_depend_on_is_refused(self):
        doc = self.receive(self.rice, 10, 100)
        self.sale(self.rice, 8, 300)
        with self.assertRaises(Conflict):
            stockdocs.cancel_doc(self.dehyar, doc)
        self.assertEqual(self.stock(self.rice), 2)
        other = self.receive(self.oil, 5, 10)
        stockdocs.cancel_doc(self.dehyar, other)
        self.assertEqual(self.stock(self.oil), 0)

    def test_numbers_restart_per_kind_and_year_and_dates_are_checked(self):
        a, b = self.receive(self.rice, 1, 1), self.receive(self.oil, 1, 1)
        issue = stockdocs.create_doc(self.dehyar, self.year, 'issue', D2, self.wh, [{'product': self.rice, 'qty': 1}])
        self.assertEqual((a.number, b.number, issue.number), (1, 2, 1))
        with self.assertRaises(Invalid):
            self.receive(self.rice, 1, 1, date(2020, 1, 1))
        self.year.is_closed = True
        self.year.save()
        with self.assertRaises(Conflict):
            self.receive(self.rice, 1, 1)

    def test_duplicate_products_bad_quantities_and_the_date_lock(self):
        with self.assertRaises(Invalid):
            stockdocs.create_doc(self.dehyar, self.year, 'receipt', D1, self.wh, [{'product': self.rice, 'qty': 1}, {'product': self.rice, 'qty': 2}])
        for qty in (0, -1, 'x', '1.2345'):
            with self.assertRaises(Invalid):
                self.receive(self.rice, qty, 1)
        controls.set_lock(self.dehyar, D2)
        with self.assertRaises(Conflict):
            self.receive(self.rice, 1, 1, D1)
        self.assertTrue(self.receive(self.rice, 1, 1, D3))


class InvoiceTests(TradeBase):
    def setUp(self):
        super().setUp()
        self.receive(self.rice, 100, 100)

    def test_a_sale_moves_stock_totals_and_numbers(self):
        inv = invoices.create_invoice(self.dehyar, self.year, 'sale', D3, self.customer,
                                      [{'product': self.rice, 'qty': 10, 'unit_price': 150, 'discount': 100}], discount=50, tax=0)
        self.assertEqual((inv.number, inv.subtotal, inv.discount, inv.total), (1, 1400, 50, 1350))
        self.assertEqual(self.stock(self.rice), 90)
        self.assertEqual(self.sale(self.rice, 1, 150).number, 2)

    def test_vat_comes_from_the_settings(self):
        invoices.update_settings(self.dehyar, vat_percent='10')
        inv = self.sale(self.rice, 10, 100)
        self.assertEqual((inv.tax, inv.total), (100, 1100))

    def test_shortage_is_refused_unless_allowed(self):
        with self.assertRaises(Conflict):
            self.sale(self.rice, 101, 150)
        inv = self.sale(self.rice, 101, 150, allow_shortage=True)
        self.assertEqual(self.stock(self.rice), -1)
        self.assertTrue(inv)

    def test_purchase_adds_stock_at_the_net_price_and_sets_the_average(self):
        invoices.create_invoice(self.dehyar, self.year, 'purchase', D2, self.supplier,
                                [{'product': self.rice, 'qty': 100, 'unit_price': 200}])
        value = inventory.valuation(self.muni, self.rice)
        self.assertEqual((value['qty'], value['avg']), (200, 150))

    def test_returns_move_stock_back_and_forth(self):
        sale = self.sale(self.rice, 10, 150)
        invoices.create_invoice(self.dehyar, self.year, 'sale_return', D4, self.customer, [{'product': self.rice, 'qty': 4, 'unit_price': 150}])
        self.assertEqual(self.stock(self.rice), 94)
        invoices.create_invoice(self.dehyar, self.year, 'purchase_return', D4, self.supplier, [{'product': self.rice, 'qty': 4, 'unit_price': 100}])
        self.assertEqual(self.stock(self.rice), 90)
        self.assertEqual(sale.number, 1)

    def test_proforma_and_order_do_not_touch_stock_and_convert_to_a_sale(self):
        proforma = invoices.create_invoice(self.dehyar, self.year, 'proforma', D2, self.customer,
                                           [{'product': self.rice, 'qty': 20, 'unit_price': 150}])
        self.assertEqual(self.stock(self.rice), 100)
        sale = invoices.convert(self.dehyar, proforma, D3)
        proforma.refresh_from_db()
        self.assertEqual((sale.kind, sale.source_id, proforma.status), ('sale', proforma.id, 'converted'))
        self.assertEqual(self.stock(self.rice), 80)
        with self.assertRaises(Conflict):
            invoices.convert(self.dehyar, proforma, D3)
        invoices.cancel_invoice(self.dehyar, sale)
        proforma.refresh_from_db()
        self.assertEqual((proforma.status, self.stock(self.rice)), ('issued', 100))

    def test_payments_cannot_exceed_the_total_and_only_apply_to_sales_and_purchases(self):
        inv = self.sale(self.rice, 10, 100)
        invoices.add_payment(self.dehyar, inv, D3, 400, 'cash')
        self.assertEqual(invoices.remaining_of(inv), 600)
        with self.assertRaises(Conflict):
            invoices.add_payment(self.dehyar, inv, D3, 601, 'cash')
        with self.assertRaises(Invalid):
            invoices.add_payment(self.dehyar, inv, date(2025, 3, 25), 1, 'cash')
        proforma = invoices.create_invoice(self.dehyar, self.year, 'proforma', D2, self.customer, [{'product': self.rice, 'qty': 1, 'unit_price': 1}])
        with self.assertRaises(Conflict):
            invoices.add_payment(self.dehyar, proforma, D3, 1, 'cash')

    def test_cancelling_returns_the_stock_but_needs_payments_removed_first(self):
        inv = self.sale(self.rice, 10, 100, paid=1000)
        with self.assertRaises(Conflict):
            invoices.cancel_invoice(self.dehyar, inv)
        invoices.delete_payment(self.dehyar, inv.payments.get())
        invoices.cancel_invoice(self.dehyar, inv)
        self.assertEqual((self.stock(self.rice), Invoice.objects.get(pk=inv.pk).status), (100, 'canceled'))
        with self.assertRaises(Conflict):
            invoices.cancel_invoice(self.dehyar, inv)

    def test_cancelling_a_purchase_that_sales_depend_on_is_refused(self):
        purchase = invoices.create_invoice(self.dehyar, self.year, 'purchase', D2, self.supplier, [{'product': self.oil, 'qty': 5, 'unit_price': 10}])
        self.sale(self.oil, 5, 900)
        with self.assertRaises(Conflict):
            invoices.cancel_invoice(self.dehyar, purchase)
        self.assertEqual(Invoice.objects.get(pk=purchase.pk).status, 'issued')

    def test_validation(self):
        bad_calls = [
            dict(lines=[]),
            dict(lines=[{'product': self.rice, 'qty': 0, 'unit_price': 1}]),
            dict(lines=[{'product': self.rice, 'qty': 1, 'unit_price': 1, 'discount': 5}]),
            dict(lines=[{'product': self.rice, 'qty': 1, 'unit_price': 10}, {'product': self.rice, 'qty': 1, 'unit_price': 10}]),
            dict(lines=[{'product': self.rice, 'qty': 1, 'unit_price': 10}], discount=11),
            dict(lines=[{'product': self.rice, 'qty': 1, 'unit_price': 10}], paid=11),
        ]
        for kwargs in bad_calls:
            with self.subTest(kwargs=kwargs), self.assertRaises(Invalid):
                invoices.create_invoice(self.dehyar, self.year, 'sale', D3, self.customer, **kwargs)
        self.rice.is_active = False
        self.rice.save()
        with self.assertRaises(Invalid):
            self.sale(self.rice, 1, 1)

    def test_the_date_lock_and_closed_year_apply(self):
        controls.set_lock(self.dehyar, D3)
        with self.assertRaises(Conflict):
            self.sale(self.rice, 1, 1, D3)
        self.assertTrue(self.sale(self.rice, 1, 1, D4))

    def test_other_municipalities_cannot_use_my_documents(self):
        inv = self.sale(self.rice, 1, 150)
        other = make_user('dehyari')
        make_municipality(other)
        with self.assertRaises(Exception):
            invoices.get_invoice(other, inv.pk)
        with self.assertRaises(Exception):
            invoices.cancel_invoice(other, inv)


class QuickSaleTests(TradeBase):
    def test_a_quick_sale_is_paid_in_full_to_the_cash_customer(self):
        self.receive(self.rice, 10, 100)
        inv = invoices.quick_sale(self.dehyar, self.year, [{'product': self.rice, 'qty': 2}], on=D3)
        self.assertEqual((inv.party.name, inv.total, invoices.remaining_of(inv), self.stock(self.rice)), ('مشتری نقدی', 300, 0, 8))
        again = invoices.quick_sale(self.dehyar, self.year, [{'product': self.rice, 'qty': 1, 'unit_price': 120}], on=D3)
        self.assertEqual((again.party_id, again.total), (inv.party_id, 120))
        self.assertEqual(Party.objects.filter(municipality=self.muni, name='مشتری نقدی').count(), 1)

    def test_vat_is_added_and_paid(self):
        invoices.update_settings(self.dehyar, vat_percent='10')
        self.receive(self.rice, 10, 100)
        inv = invoices.quick_sale(self.dehyar, self.year, [{'product': self.rice, 'qty': 2}], on=D3)
        self.assertEqual((inv.total, invoices.paid_of(inv)), (330, 330))

    def test_out_of_stock_is_refused(self):
        with self.assertRaises(Conflict):
            invoices.quick_sale(self.dehyar, self.year, [{'product': self.rice, 'qty': 1}], on=D3)


class ProductionTests(TradeBase):
    def setUp(self):
        super().setUp()
        self.cake = inventory.create_product(self.dehyar, code='C1', name='کیک')
        self.receive(self.rice, 100, 100)
        self.receive(self.oil, 10, 400)
        self.formula = production.create_formula(self.dehyar, self.cake, 10, [{'product': self.rice, 'qty': 5}, {'product': self.oil, 'qty': 1}])

    def test_a_run_consumes_components_and_stocks_the_product_at_their_cost(self):
        run = production.run_production(self.dehyar, self.year, self.formula, 2, D3)
        self.assertEqual((self.stock(self.rice), self.stock(self.oil), self.stock(self.cake)), (90, 8, 20))
        self.assertEqual(run.unit_cost, Decimal('90'))                              # (10*100 + 2*400) / 20
        self.assertEqual(inventory.valuation(self.muni, self.cake)['avg'], 90)

    def test_estimate_shows_needs_shortage_and_how_many_batches_fit(self):
        data = production.estimate(self.dehyar, self.formula, 3)
        self.assertEqual((data['output'], data['cost'], data['short'], data['possible_batches']), (30, 2700 + 0, False, 10))
        short = production.estimate(self.dehyar, self.formula, 11)
        self.assertTrue(short['short'])

    def test_shortage_blocks_a_run_and_cancelling_is_checked(self):
        with self.assertRaises(Conflict):
            production.run_production(self.dehyar, self.year, self.formula, 11, D3)
        run = production.run_production(self.dehyar, self.year, self.formula, 1, D3)
        self.sale(self.cake, 10, 500)
        with self.assertRaises(Conflict):
            production.cancel_run(self.dehyar, run)

    def test_cancel_restores_the_components(self):
        run = production.run_production(self.dehyar, self.year, self.formula, 1, D3)
        production.cancel_run(self.dehyar, run)
        self.assertEqual((self.stock(self.rice), self.stock(self.cake)), (100, 0))

    def test_formula_validation_and_deletion(self):
        for components in ([], [{'product': self.cake, 'qty': 1}], [{'product': self.rice, 'qty': 1}, {'product': self.rice, 'qty': 2}]):
            with self.assertRaises(Invalid):
                production.create_formula(self.dehyar, self.cake, 1, components)
        production.run_production(self.dehyar, self.year, self.formula, 1, D3)
        with self.assertRaises(Conflict):
            production.delete_formula(self.dehyar, self.formula)
        production.set_formula_active(self.dehyar, self.formula, False)
        with self.assertRaises(Conflict):
            production.run_production(self.dehyar, self.year, self.formula, 1, D3)


class ConsignmentTests(TradeBase):
    def setUp(self):
        super().setUp()
        self.receive(self.rice, 10, 100)

    def test_given_goods_leave_stock_and_come_back_at_the_average(self):
        c = consignment.create_consignment(self.dehyar, 'given', D2, self.customer, [{'product': self.rice, 'qty': 6}])
        self.assertEqual(self.stock(self.rice), 4)
        consignment.give_back(self.dehyar, c, D3, {c.lines.get().id: 2})
        self.assertEqual(self.stock(self.rice), 6)
        c.refresh_from_db()
        self.assertEqual(c.status, 'open')
        consignment.give_back(self.dehyar, c, D3, {c.lines.get().id: 4})
        c.refresh_from_db()
        self.assertEqual((c.status, self.stock(self.rice)), ('closed', 10))

    def test_cannot_give_more_than_stock_or_return_more_than_open(self):
        with self.assertRaises(Conflict):
            consignment.create_consignment(self.dehyar, 'given', D2, self.customer, [{'product': self.rice, 'qty': 11}])
        c = consignment.create_consignment(self.dehyar, 'given', D2, self.customer, [{'product': self.rice, 'qty': 3}])
        with self.assertRaises(Conflict):
            consignment.give_back(self.dehyar, c, D3, {c.lines.get().id: 4})
        with self.assertRaises(Invalid):
            consignment.give_back(self.dehyar, c, D3, {})

    def test_taken_goods_are_a_memo_and_do_not_change_stock(self):
        c = consignment.create_consignment(self.dehyar, 'taken', D2, self.supplier, [{'product': self.oil, 'qty': 5}])
        self.assertEqual(self.stock(self.oil), 0)
        consignment.close(self.dehyar, c)
        self.assertEqual(c.status, 'closed')

    def test_cancelling_restores_stock_unless_goods_came_back(self):
        c = consignment.create_consignment(self.dehyar, 'given', D2, self.customer, [{'product': self.rice, 'qty': 6}])
        consignment.cancel(self.dehyar, c)
        self.assertEqual(self.stock(self.rice), 10)
        d = consignment.create_consignment(self.dehyar, 'given', D2, self.customer, [{'product': self.rice, 'qty': 6}])
        consignment.give_back(self.dehyar, d, D3, {d.lines.get().id: 1})
        with self.assertRaises(Conflict):
            consignment.cancel(self.dehyar, d)


class PostingTests(TradeBase):
    def setUp(self):
        super().setUp()
        mk = lambda code, title, kind, nature, **kw: Account.objects.create(municipality=self.muni, code=code, title=title, kind=kind,
                                                                            nature=nature, **kw)
        self.receivable = mk('113', 'بدهکاران', 'asset', 'debit', requires_party=True)
        self.payable = mk('311', 'بستانکاران', 'liability', 'credit', requires_party=True)
        self.inventory_account = mk('117', 'موجودی کالا', 'asset', 'debit')
        self.sales = mk('5010101009', 'فروش کالا', 'budget_resource', 'credit')
        self.cogs = mk('6010101009', 'بهای تمام‌شده', 'budget_use', 'debit')
        self.vat = mk('313', 'مالیات پرداختنی', 'liability', 'credit')
        invoices.update_settings(self.dehyar, receivable_account=self.receivable, payable_account=self.payable, sales_account=self.sales,
                                 inventory_account=self.inventory_account, cogs_account=self.cogs, tax_account=self.vat, vat_percent='10')
        self.receive(self.rice, 100, 100)

    def by_account(self, voucher):
        out = {}
        for line in voucher.lines.all():
            out.setdefault(line.account.code, []).append((line.debit, line.credit))
        return out

    def test_a_sale_posts_receivable_sales_vat_and_cost_of_goods(self):
        inv = self.sale(self.rice, 10, 150)                                            # net 1500, VAT 150, cost 10 * 100
        voucher = posting.post_invoice(self.dehyar, inv)
        self.assertEqual(self.by_account(voucher), {'113': [(1650, 0)], '5010101009': [(0, 1500)], '313': [(0, 150)],
                                                    '6010101009': [(1000, 0)], '117': [(0, 1000)]})
        self.assertTrue(ledger.is_balanced(voucher))
        inv.refresh_from_db()
        self.assertEqual((voucher.status, inv.voucher_id), ('temporary', voucher.id))
        self.assertEqual(voucher.lines.get(account=self.receivable).party, self.customer)

    def test_a_purchase_posts_inventory_and_payable(self):
        inv = invoices.create_invoice(self.dehyar, self.year, 'purchase', D2, self.supplier, [{'product': self.rice, 'qty': 10, 'unit_price': 100}])
        voucher = posting.post_invoice(self.dehyar, inv)
        self.assertEqual(self.by_account(voucher), {'117': [(1000, 0)], '313': [(100, 0)], '311': [(0, 1100)]})

    def test_returns_mirror_the_originals(self):
        inv = invoices.create_invoice(self.dehyar, self.year, 'sale_return', D4, self.customer, [{'product': self.rice, 'qty': 2, 'unit_price': 150}])
        voucher = posting.post_invoice(self.dehyar, inv)
        by = self.by_account(voucher)
        self.assertEqual(by['5010101009'], [(300, 0)])
        self.assertEqual(by['113'], [(0, 330)])
        self.assertTrue(ledger.is_balanced(voucher))

    def test_payments_post_with_the_invoice_and_afterwards(self):
        inv = self.sale(self.rice, 10, 150)
        invoices.add_payment(self.dehyar, inv, D3, 500, 'cash', self.bank)
        voucher = posting.post_invoice(self.dehyar, inv)
        payment = inv.payments.get()
        self.assertIsNotNone(payment.voucher_id)
        self.assertEqual(self.by_account(payment.voucher), {'1120101': [(500, 0)], '113': [(0, 500)]})
        later = invoices.add_payment(self.dehyar, inv, D4, 100, 'cash', self.bank)
        self.assertIsNotNone(later.voucher_id)
        self.assertEqual(voucher.status, 'temporary')

    def test_unposting_and_cancelling_remove_the_vouchers(self):
        inv = self.sale(self.rice, 1, 150)
        posting.post_invoice(self.dehyar, inv)
        posting.unpost_invoice(self.dehyar, inv)
        inv.refresh_from_db()
        self.assertIsNone(inv.voucher_id)
        self.assertEqual(Voucher.objects.filter(municipality=self.muni, deleted_at__isnull=True).count(), 0)
        posting.post_invoice(self.dehyar, inv)
        invoices.cancel_invoice(self.dehyar, inv)
        self.assertEqual(Voucher.objects.filter(municipality=self.muni, deleted_at__isnull=True).count(), 0)

    def test_final_vouchers_block_unposting_and_cancelling(self):
        inv = self.sale(self.rice, 1, 150)
        voucher = posting.post_invoice(self.dehyar, inv)
        ledger.finalize(self.dehyar, voucher)
        for call in (posting.unpost_invoice, invoices.cancel_invoice):
            with self.assertRaises(Conflict):
                call(self.dehyar, inv)

    def test_missing_accounts_are_named_and_proformas_are_not_posted(self):
        TradeSettings.objects.filter(municipality=self.muni).update(sales_account=None)
        inv = self.sale(self.rice, 1, 150)
        with self.assertRaises(Invalid) as caught:
            posting.post_invoice(self.dehyar, inv)
        self.assertIn('درآمد فروش', str(caught.exception))
        proforma = invoices.create_invoice(self.dehyar, self.year, 'proforma', D2, self.customer, [{'product': self.rice, 'qty': 1, 'unit_price': 1}])
        with self.assertRaises(Conflict):
            posting.post_invoice(self.dehyar, proforma)

    def test_cannot_post_twice_and_settings_are_validated(self):
        inv = self.sale(self.rice, 1, 150)
        posting.post_invoice(self.dehyar, inv)
        with self.assertRaises(Conflict):
            posting.post_invoice(self.dehyar, inv)
        with self.assertRaises(Invalid):
            invoices.update_settings(self.dehyar, vat_percent='150')
        group = Account.objects.create(municipality=self.muni, code='9', title='گروه', kind='asset', nature='debit', is_postable=False)
        with self.assertRaises(Invalid):
            invoices.update_settings(self.dehyar, sales_account=group)


class ProfitTests(TradeBase):
    def test_profit_per_product_uses_the_cost_the_goods_left_at(self):
        self.receive(self.rice, 10, 100, D1)
        self.receive(self.rice, 10, 200, D2)                                            # average 150
        invoices.create_invoice(self.dehyar, self.year, 'sale', D3, self.customer,
                                [{'product': self.rice, 'qty': 10, 'unit_price': 250}], discount=100)
        rows, totals = inventory.profit_by_product(self.dehyar, self.year)
        row = rows[0]
        self.assertEqual((row['qty'], row['revenue'], row['cost'], row['profit']), (10, 2400, 1500, 900))
        self.assertEqual(row['margin'], 38)
        self.assertEqual(totals, {'revenue': 2400, 'cost': 1500, 'profit': 900})

    def test_returns_reduce_revenue_and_cost_and_the_range_filters(self):
        self.receive(self.rice, 10, 100, D1)
        self.sale(self.rice, 4, 300, D3)
        invoices.create_invoice(self.dehyar, self.year, 'sale_return', D4, self.customer, [{'product': self.rice, 'qty': 1, 'unit_price': 300}])
        rows, totals = inventory.profit_by_product(self.dehyar, self.year)
        self.assertEqual((rows[0]['qty'], rows[0]['revenue'], rows[0]['cost']), (3, 900, 300))
        rows, _ = inventory.profit_by_product(self.dehyar, self.year, date_to=date(2025, 5, 15))
        self.assertEqual((rows[0]['qty'], rows[0]['revenue']), (4, 1200))
        self.assertEqual(inventory.profit_by_product(self.dehyar, self.year, date_from=date(2025, 7, 1))[0], [])

    def test_canceled_invoices_are_left_out(self):
        self.receive(self.rice, 10, 100)
        inv = self.sale(self.rice, 4, 300)
        invoices.cancel_invoice(self.dehyar, inv)
        self.assertEqual(inventory.profit_by_product(self.dehyar, self.year)[0], [])
