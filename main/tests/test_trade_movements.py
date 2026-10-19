"""The stock-movement module: receive, issue, transfer and reverse are the only writers of the stock log."""
from datetime import date

from main.accounting.trade import movements
from main.models import StockMove
from main.office.errors import Conflict
from main.tests.test_trade import TradeBase

D1, D2, D3 = date(2025, 4, 1), date(2025, 4, 10), date(2025, 5, 1)


class MovementTests(TradeBase):
    def test_issue_refuses_a_shortage_unless_allowed(self):
        movements.receive(self.muni, self.rice, self.wh, D1, 5, 'doc', unit_cost=100)
        with self.assertRaises(Conflict):
            movements.issue(self.muni, self.rice, self.wh, D2, 6, 'doc')
        self.assertEqual(self.stock(self.rice), 5)
        movements.issue(self.muni, self.rice, self.wh, D2, 6, 'doc', allow_shortage=True)
        self.assertEqual(self.stock(self.rice), -1)

    def test_issue_writes_one_move_per_series_taken(self):
        movements.receive(self.muni, self.rice, self.wh, D1, 3, 'doc', unit_cost=100, lot='A', expiry=date(2025, 6, 1))
        movements.receive(self.muni, self.rice, self.wh, D1, 3, 'doc', unit_cost=100, lot='B', expiry=date(2025, 7, 1))
        moves = movements.issue(self.muni, self.rice, self.wh, D2, 4, 'doc')
        self.assertEqual([(m.lot, m.qty) for m in moves], [('A', -3), ('B', -1)])

    def test_transfer_moves_stock_and_keeps_each_series(self):
        movements.receive(self.muni, self.rice, self.wh, D1, 5, 'doc', unit_cost=100, lot='A', expiry=date(2025, 6, 1))
        movements.transfer(self.muni, self.rice, self.wh, self.main, D2, 2, 'doc', unit_cost=100)
        self.assertEqual((self.stock(self.rice), self.stock(self.rice, self.main)), (3, 2))
        arrived = StockMove.objects.get(warehouse=self.main)
        self.assertEqual((arrived.lot, arrived.expiry), ('A', date(2025, 6, 1)))

    def test_reverse_refuses_when_later_movements_would_go_negative(self):
        first = movements.receive(self.muni, self.rice, self.wh, D1, 5, 'doc', unit_cost=100)[0]
        movements.issue(self.muni, self.rice, self.wh, D2, 4, 'doc')
        with self.assertRaises(Conflict):
            movements.reverse(self.muni, StockMove.objects.filter(pk=first.pk))
        self.assertEqual(self.stock(self.rice), 1)           # nothing was removed
