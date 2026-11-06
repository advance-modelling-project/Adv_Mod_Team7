"""Unit tests for the order tracker; no full-scale Mesa model is needed."""
import unittest
from types import SimpleNamespace
from config import CrateType
from fulfillment_metrics import OrderTracker


def order(id='a', qty=10, uom='RTI', step=1, lead=2):
    return SimpleNamespace(order_id=id, issuer='RDC_1' if uom == 'RTI' else 'PRO_1',
                           supplier='PRO_1' if uom == 'RTI' else 'POOL_1',
                           crate_type=CrateType.TYPE_1, quantity=qty, uom=uom,
                           creation_step=step, lead_time=lead)


class OrderTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = OrderTracker(200)

    def test_original_quantity_survives_mutable_order(self):
        o = order(qty=10)
        self.tracker.register(o)
        o.quantity = 2  # baseline mutates remaining quantity
        self.tracker.deliver(o, 8, 3)
        self.assertEqual(self.tracker.orders['a'].original_rtis, 10)
        self.assertEqual(self.tracker.orders['a'].outstanding_rtis, 2)

    def test_pooler_units_converted_to_rtis(self):
        o = order(qty=3, uom='UL')
        self.tracker.register(o)
        self.tracker.deliver(o, 2, 3)
        data = self.tracker.snapshot(3)
        self.assertEqual(data['pooler_due_rtis'], 600)
        self.assertEqual(data['pooler_on_time_rtis'], 400)
        self.assertEqual(data['pooler_outstanding_due_rtis'], 200)

    def test_on_time_and_late_partial_deliveries(self):
        o = order(qty=10)
        self.tracker.register(o)
        self.tracker.deliver(o, 4, 3)
        self.tracker.deliver(o, 6, 5)
        data = self.tracker.snapshot(5)
        self.assertEqual(data['producer_on_time_rtis'], 4)
        self.assertEqual(data['producer_late_rtis'], 6)
        self.assertEqual(data['producer_outstanding_due_rtis'], 0)
        self.assertEqual(data['producer_on_time_fill_rate_pct'], 40.0)

    def test_not_due_excluded_from_denominator(self):
        self.tracker.register(order(qty=15, step=10, lead=3))
        data = self.tracker.snapshot(12)
        self.assertEqual(data['producer_due_rtis'], 0)
        self.assertEqual(data['producer_not_yet_due_rtis'], 15)
        self.assertIsNone(data['producer_on_time_fill_rate_pct'])

    def test_due_today_cohort(self):
        x = order('x', qty=10, step=1, lead=2)
        y = order('y', qty=5, step=1, lead=3)
        self.tracker.register(x); self.tracker.register(y)
        self.tracker.deliver(x, 10, 3)
        data = self.tracker.snapshot(3)
        self.assertEqual(data['producer_due_today_rtis'], 10)
        self.assertEqual(data['producer_on_time_due_today_rtis'], 10)
        self.assertEqual(data['producer_due_today_fill_rate_pct'], 100)

    def test_cannot_overdeliver(self):
        o = order(qty=5)
        self.tracker.register(o)
        with self.assertRaises(ValueError):
            self.tracker.deliver(o, 6, 3)

    def test_audit_balances(self):
        o = order(qty=20)
        self.tracker.register(o)
        self.tracker.deliver(o, 5, 3)
        r = self.tracker.audit_rows(3)[0]
        self.assertEqual(r['Original RTIs'], r['On Time RTIs'] + r['Late RTIs'] + r['Outstanding RTIs'])
        self.assertEqual(r['Status'], 'outstanding_due')

    def test_duplicate_ids_rejected(self):
        self.tracker.register(order())
        with self.assertRaises(ValueError):
            self.tracker.register(order())


if __name__ == '__main__':
    unittest.main()
