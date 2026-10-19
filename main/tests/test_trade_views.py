"""Trade screens: tabs, line-table forms, point of sale, invoice actions, print, exports, access and tenant isolation."""
from datetime import date

from django.urls import reverse

from main.accounting import builder
from main.accounting.trade import inventory, invoices, production
from main.models import Account, Consignment, Invoice, Product, StockDoc
from main.tests.helpers import client_for, make_municipality
from main.tests.test_accounting_ledger import make_user
from main.tests.test_trade import TradeBase

TABS = ('trade_products', 'trade_invoices', 'trade_pos', 'trade_stock', 'trade_docs', 'trade_production', 'trade_consign', 'trade_profit')
ON = '1404/02/11'  # 2025-05-01, inside 1404


def u(name, *args):
    return reverse(f'main:{name}', args=args)


class TradeViewBase(TradeBase):
    def assertDone(self, response):
        self.assertEqual(response.status_code, 204, response.headers.get('HX-Trigger') or response.content.decode()[:900])

    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)
        self.receive(self.rice, 100, 100, date(2025, 4, 1))


class TabTests(TradeViewBase):
    def test_every_tab_renders(self):
        self.sale(self.rice, 5, 300)
        for tab in TABS:
            with self.subTest(tab=tab):
                response = self.client.get(u('acc_panel'), {'tab': tab, 'year': self.year.id})
                self.assertEqual(response.status_code, 200)

    def test_pos_tab_has_the_products_and_the_profit_tab_has_numbers(self):
        self.assertContains(self.client.get(u('acc_panel'), {'tab': 'trade_pos', 'year': self.year.id}), 'data-pos')
        self.sale(self.rice, 10, 300)
        profit = self.client.get(u('acc_panel'), {'tab': 'trade_profit', 'year': self.year.id})
        self.assertContains(profit, 'برنج')

    def test_citizens_and_anonymous_are_kept_out(self):
        for who in (client_for(), client_for(make_user('citizen'))):
            self.assertIn(who.get(u('acc_p_trade_warehouses')).status_code, (302, 403, 404))
            self.assertIn(who.get(u('acc_p_trade_product_new')).status_code, (302, 403, 404))


class ProductViewTests(TradeViewBase):
    def test_create_edit_and_kardex(self):
        response = self.client.post(u('acc_p_trade_product_new'), {'code': 'P9', 'name': 'شکر', 'unit': 'کیلو', 'sell_price': '۱٬۲۰۰'})
        self.assertEqual(response.status_code, 204)
        sugar = Product.objects.get(municipality=self.muni, code='P9')
        self.assertEqual(sugar.sell_price, 1200)
        self.assertEqual(self.client.get(u('acc_p_trade_product_edit', sugar.id)).status_code, 200)
        self.assertContains(self.client.get(u('acc_p_trade_kardex', self.rice.id)), 'برنج')

    def test_duplicate_code_is_shown_in_the_form(self):
        response = self.client.post(u('acc_p_trade_product_new'), {'code': 'P1', 'name': 'تکراری', 'unit': 'عدد'})
        self.assertGreaterEqual(response.status_code, 400)

    def test_other_municipalities_products_are_hidden(self):
        other = make_user('dehyari')
        make_municipality(other)
        theirs = inventory.create_product(other, code='X1', name='کالای دیگران', sell_price=1)
        self.assertEqual(self.client.get(u('acc_p_trade_kardex', theirs.id)).status_code, 404)
        self.assertEqual(self.client.get(u('acc_p_trade_product_edit', theirs.id)).status_code, 404)


class InvoiceViewTests(TradeViewBase):
    def post_sale(self, **extra):
        data = {'on': ON, 'party': self.customer.id, 'warehouse': self.wh.id, 'product': [self.rice.id], 'qty': ['4'],
                'unit_price': ['۳۰۰'], 'discount': ['']}
        data.update(extra)
        return self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'sale'), data)

    def test_forms_open_for_every_kind(self):
        for kind, _ in Invoice.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(u('acc_p_trade_invoice_new', self.year.id, kind)).status_code, 200)
        self.assertEqual(self.client.get(u('acc_p_trade_invoice_new', self.year.id, 'nonsense')).status_code, 404)

    def test_sale_is_created_and_moves_stock(self):
        self.assertEqual(self.post_sale().status_code, 204)
        inv = Invoice.objects.get(municipality=self.muni, kind='sale')
        self.assertEqual(inv.total, 1200)
        self.assertEqual(self.stock(self.rice), 96)

    def test_empty_and_bad_rows_come_back_to_the_form(self):
        empty = self.client.post(u('acc_p_trade_invoice_new', self.year.id, 'sale'),
                                 {'on': ON, 'party': self.customer.id, 'product': [''], 'qty': [''], 'unit_price': [''], 'discount': ['']})
        self.assertGreaterEqual(empty.status_code, 400)
        unknown = self.post_sale(product=['999999'])
        self.assertGreaterEqual(unknown.status_code, 400)
        self.assertFalse(Invoice.objects.filter(municipality=self.muni).exists())

    def test_shortage_is_refused(self):
        response = self.post_sale(qty=['500'])
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.stock(self.rice), 100)

    def test_detail_payment_post_unpost_print_and_cancel(self):
        inv = self.sale(self.rice, 4, 300)
        self.assertContains(self.client.get(u('acc_p_trade_invoice', inv.id)), 'برنج')
        pay = self.client.post(u('acc_p_trade_invoice_pay', inv.id), {'date': ON, 'amount': '500', 'method': 'cash'})
        self.assertEqual(pay.status_code, 200)
        self.assertEqual(invoices.paid_of(inv), 500)
        self.assertEqual(self.client.post(u('acc_p_trade_payment_delete', inv.payments.first().id)).status_code, 200)
        self.assertEqual(invoices.paid_of(inv), 0)
        refused = self.client.post(u('acc_p_trade_invoice_action', inv.id, 'post'))
        self.assertEqual(refused.status_code, 400)
        names = ('receivable_account', 'payable_account', 'sales_account', 'inventory_account', 'cogs_account', 'tax_account')
        accounts = [Account.objects.create(municipality=self.muni, code=f'9{i}', title=f'حساب {i}', kind='asset', nature='debit')
                    for i in range(len(names))]
        invoices.update_settings(self.dehyar, **dict(zip(names, accounts)))
        self.assertDone(self.client.post(u('acc_p_trade_invoice_action', inv.id, 'post')))
        inv.refresh_from_db()
        self.assertIsNotNone(inv.voucher_id)
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_action', inv.id, 'unpost')).status_code, 204)
        printed = self.client.get(u('acc_p_trade_print', inv.id), {'paper': 'A5'})
        self.assertContains(printed, 'برنج')
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_action', inv.id, 'cancel')).status_code, 204)
        self.assertEqual(self.stock(self.rice), 100)
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_action', inv.id, 'nonsense')).status_code, 404)

    def test_proforma_converts(self):
        pro = invoices.create_invoice(self.dehyar, self.year, 'proforma', date(2025, 5, 1), self.customer,
                                      [{'product': self.rice, 'qty': 2, 'unit_price': 300}])
        self.assertEqual(self.stock(self.rice), 100)
        self.assertEqual(self.client.post(u('acc_p_trade_invoice_action', pro.id, 'convert')).status_code, 204)
        self.assertEqual(self.stock(self.rice), 98)

    def test_actions_need_post(self):
        inv = self.sale(self.rice, 1, 300)
        self.assertEqual(self.client.get(u('acc_p_trade_invoice_action', inv.id, 'cancel')).status_code, 405)

    def test_other_municipalities_invoices_are_hidden(self):
        other = make_user('dehyari')
        make_municipality(other)
        inv = self.sale(self.rice, 1, 300)
        foreign = client_for(other)
        for name in ('acc_p_trade_invoice', 'acc_p_trade_print'):
            self.assertEqual(foreign.get(u(name, inv.id)).status_code, 404)
        self.assertEqual(foreign.post(u('acc_p_trade_invoice_action', inv.id, 'cancel')).status_code, 404)

    def test_settings_form(self):
        self.assertEqual(self.client.get(u('acc_p_trade_settings')).status_code, 200)
        response = self.client.post(u('acc_p_trade_settings'), {'vat_percent': '۹', 'allow_shortage': 'on'})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(invoices.settings_of(self.dehyar).vat_percent, 9)


class PosViewTests(TradeViewBase):
    def test_quick_sale_from_the_cart(self):
        response = self.client.post(u('acc_p_trade_pos_sale', self.year.id), {
            'date': ON, 'method': 'cash', 'product': [self.rice.id], 'qty': ['3'], 'unit_price': ['300']})
        self.assertDone(response)
        inv = Invoice.objects.get(municipality=self.muni, kind='sale')
        self.assertEqual(inv.total, 900)
        self.assertEqual(invoices.paid_of(inv), 900)
        self.assertEqual(self.stock(self.rice), 97)

    def test_empty_cart_is_refused(self):
        self.assertGreaterEqual(self.client.post(u('acc_p_trade_pos_sale', self.year.id), {'date': ON}).status_code, 400)
        self.assertFalse(Invoice.objects.filter(municipality=self.muni).exists())

    def test_barcode_lookup(self):
        self.rice.barcode = '6260001'
        self.rice.save()
        found = self.client.get(u('acc_p_trade_find'), {'q': '6260001'})
        self.assertTrue(found.json()['found'])
        self.assertEqual(found.json()['name'], 'برنج')
        self.assertFalse(self.client.get(u('acc_p_trade_find'), {'q': 'zzz-none'}).json()['found'])


class StockViewTests(TradeViewBase):
    def test_documents_receipt_issue_transfer_stocktake_and_cancel(self):
        base = {'on': ON, 'warehouse': self.wh.id}
        receipt = self.client.post(u('acc_p_trade_doc_new', self.year.id, 'receipt'),
                                   {**base, 'product': [self.oil.id], 'qty': ['10'], 'unit_cost': ['500']})
        self.assertEqual(receipt.status_code, 204)
        self.assertEqual(self.stock(self.oil), 10)
        self.assertEqual(self.client.post(u('acc_p_trade_doc_new', self.year.id, 'issue'),
                                          {**base, 'product': [self.oil.id], 'qty': ['3']}).status_code, 204)
        self.assertEqual(self.client.post(u('acc_p_trade_doc_new', self.year.id, 'transfer'),
                                          {**base, 'to_warehouse': self.main.id, 'product': [self.oil.id], 'qty': ['2']}).status_code, 204)
        self.assertEqual((self.stock(self.oil), self.stock(self.oil, self.main)), (5, 2))
        self.assertDone(self.client.post(u('acc_p_trade_doc_new', self.year.id, 'stocktake'),
                                         {**base, 'product': [self.oil.id], 'counted': ['4']}))
        self.assertEqual(self.stock(self.oil), 4)
        doc = StockDoc.objects.filter(municipality=self.muni, kind='receipt').order_by('-id').first()
        self.assertContains(self.client.get(u('acc_p_trade_doc', doc.id)), 'روغن')

    def test_issue_beyond_stock_is_refused(self):
        response = self.client.post(u('acc_p_trade_doc_new', self.year.id, 'issue'),
                                    {'on': ON, 'warehouse': self.wh.id, 'product': [self.rice.id], 'qty': ['1000']})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.stock(self.rice), 100)

    def test_unknown_document_kind_is_404(self):
        self.assertEqual(self.client.get(u('acc_p_trade_doc_new', self.year.id, 'nonsense')).status_code, 404)

    def test_cancel_a_document(self):
        doc = self.receive(self.oil, 5, 100, date(2025, 5, 1))
        self.assertEqual(self.client.post(u('acc_p_trade_doc_cancel', doc.id)).status_code, 204)
        self.assertEqual(self.stock(self.oil), 0)

    def test_warehouses_modal_adds_a_warehouse(self):
        self.assertContains(self.client.get(u('acc_p_trade_warehouses')), 'انبار دوم')
        response = self.client.post(u('acc_p_trade_warehouses'), {'code': '3', 'name': 'انبار سوم'})
        self.assertContains(response, 'انبار سوم')

    def test_exports_are_spreadsheets(self):
        self.sale(self.rice, 5, 300)
        for name in ('acc_p_trade_stock_export', 'acc_p_trade_profit_export'):
            response = self.client.get(u(name, self.year.id))
            self.assertEqual(response.status_code, 200)
            self.assertIn('spreadsheetml', response['Content-Type'])


class ProductionViewTests(TradeViewBase):
    def test_formula_and_run(self):
        flour = inventory.create_product(self.dehyar, code='M1', name='آرد', buy_price=10, sell_price=20)
        self.receive(flour, 100, 10, date(2025, 4, 1))
        bread = inventory.create_product(self.dehyar, code='M2', name='نان', sell_price=50)
        created = self.client.post(u('acc_p_trade_formula_new'), {'product': bread.id, 'output_qty': '10', 'note': '',
                                                                   'qty': ['5'], **{'product_': ''}})
        self.assertGreaterEqual(created.status_code, 200)
        formula = production.create_formula(self.dehyar, bread, 10, [{'product': flour, 'qty': 5}])
        self.assertEqual(self.client.get(u('acc_p_trade_run_new', self.year.id, formula.id)).status_code, 200)
        run = self.client.post(u('acc_p_trade_run_new', self.year.id, formula.id), {'date': ON, 'batches': '2'})
        self.assertEqual(run.status_code, 204)
        self.assertEqual((self.stock(flour), self.stock(bread)), (90, 20))

    def test_formula_actions_need_post(self):
        bread = inventory.create_product(self.dehyar, code='M2', name='نان', sell_price=50)
        formula = production.create_formula(self.dehyar, bread, 10, [{'product': self.rice, 'qty': 5}])
        self.assertEqual(self.client.get(u('acc_p_trade_formula_action', formula.id, 'delete')).status_code, 405)


class ConsignViewTests(TradeViewBase):
    def test_given_consignment_and_return(self):
        form = self.client.get(u('acc_p_trade_consign_new', 'given'))
        self.assertEqual(form.status_code, 200)
        response = self.client.post(u('acc_p_trade_consign_new', 'given'), {
            'on': ON, 'party': self.customer.id, 'warehouse': self.wh.id, 'product': [self.rice.id], 'qty': ['10']})
        self.assertEqual(response.status_code, 204)
        c = Consignment.objects.get(municipality=self.muni)
        self.assertEqual(self.stock(self.rice), 90)
        self.assertContains(self.client.get(u('acc_p_trade_consign', c.id)), 'برنج')
        line = c.lines.first()
        back = self.client.post(u('acc_p_trade_consign_action', c.id, 'return'), {'date': ON, f'ret_{line.id}': '4'})
        self.assertEqual(back.status_code, 200)
        self.assertEqual(self.stock(self.rice), 94)
        self.assertEqual(self.client.post(u('acc_p_trade_consign_action', c.id, 'nonsense')).status_code, 404)

    def test_unknown_kind_is_404(self):
        self.assertEqual(self.client.get(u('acc_p_trade_consign_new', 'nonsense')).status_code, 404)


class BuilderAndSearchTests(TradeViewBase):
    def test_datasets_run(self):
        self.sale(self.rice, 5, 300)
        for name, measure, dim in (('invoices', 'total', 'kind'), ('invoice_lines', 'qty', 'product'), ('stock_moves', 'qty', 'product')):
            with self.subTest(dataset=name):
                result = builder.build(self.dehyar, self.year, name, dim, measure=measure)
                self.assertTrue(result['rows'])

    def test_search_finds_products_and_invoices(self):
        from main.accounting import search
        inv = self.sale(self.rice, 1, 300)
        kinds = {r['kind'] for r in search.run(self.dehyar, 'برنج')}
        self.assertIn('کالا', kinds)
        self.assertTrue([r for r in search.run(self.dehyar, 'مشتری') if 'فروش' in r['kind']])
        self.assertTrue([r for r in search.run(self.dehyar, str(inv.number).zfill(2)) if 'فروش' in r['kind']])
