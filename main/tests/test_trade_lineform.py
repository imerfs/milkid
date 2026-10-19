"""Line-table forms: the column kinds decide how a posted cell is read."""
from datetime import date

from django.http import QueryDict
from django.test import SimpleTestCase

from main.office.errors import Invalid
from main.tests.test_trade import TradeBase
from main.views.trade_lineform import num, posted_rows, read_cell, read_lines

COLUMNS = [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty'), ('unit_price', 'قیمت', 'money'), ('lot', 'سری', 'text'),
           ('expiry', 'انقضا', 'date'), ('margin', 'سود', 'pct')]


class CellTests(SimpleTestCase):
    def test_each_kind_is_read_its_own_way(self):
        self.assertEqual(read_cell('money', '۱٬۲۵۰٬۰۰۰'), 1_250_000)
        self.assertEqual(read_cell('qty', '۲٫۵'), '2.5')
        self.assertEqual(read_cell('text', ' L-۷ '), ' L-۷ ')            # text is kept as typed
        self.assertEqual(read_cell('date', '1404/02/11'), date(2025, 5, 1))
        self.assertIsNone(read_cell('date', ''))
        self.assertEqual(num('۱۲٬۵'), '125')

    def test_bad_money_and_date_are_refused(self):
        with self.assertRaises(Invalid):
            read_cell('money', '12.5')
        with self.assertRaises(Invalid):
            read_cell('date', 'tomorrow')


class LinesTests(TradeBase):
    def post(self, **columns):
        q = QueryDict(mutable=True)
        for name, values in columns.items():
            q.setlist(name, values)
        return q

    def test_rows_are_read_with_their_kinds_and_blank_rows_skipped(self):
        post = self.post(product=[str(self.rice.id), '', str(self.oil.id)], qty=['3', '', '1'], unit_price=['۱۰۰', '', '۲۰۰'],
                         lot=['A', '', ''], expiry=['1404/02/11', '', ''], margin=['20', '', ''])
        rows = read_lines(post, self.muni, COLUMNS)
        self.assertEqual([r['product'] for r in rows], [self.rice, self.oil])
        self.assertEqual((rows[0]['qty'], rows[0]['unit_price'], rows[0]['lot'], rows[0]['expiry']), ('3', 100, 'A', date(2025, 5, 1)))
        self.assertIsNone(rows[1]['expiry'])

    def test_a_row_without_a_known_product_is_refused(self):
        with self.assertRaises(Invalid):
            read_lines(self.post(product=['999999'], qty=['1'], unit_price=['1'], lot=[''], expiry=[''], margin=['']), self.muni, COLUMNS)

    def test_posted_rows_keep_every_cell_for_redrawing(self):
        rows = posted_rows(self.post(product=['1', '2'], qty=['3']), ['product', 'qty'])
        self.assertEqual(rows, [{'product': '1', 'qty': '3'}, {'product': '2', 'qty': ''}])
