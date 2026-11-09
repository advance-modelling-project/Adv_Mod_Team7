"""Tests for the RFID traceability decision rules."""
import unittest
from types import SimpleNamespace

from agents import Pooler_Agent, Producer_Agent, RTI_Agent, _ul_dirty_history_count
from config import CrateType, LocationType, SimulationConfig, UnitLoad


def rti(age=0, dirty_product=False):
    product = SimpleNamespace(makes_dirty=True) if dirty_product else None
    return SimpleNamespace(
        detention_time=age, product=product, under_processing=False,
        location=LocationType.PRO, arrival_step=0,
    )


def ul(age=0, dirty_product=False):
    return UnitLoad(CrateType.TYPE_1, [rti(age, dirty_product)])


class TraceabilityPolicyTests(unittest.TestCase):
    def test_dirty_history_uses_product_tag_not_hidden_dirty_flag(self):
        clean = ul(dirty_product=False)
        dirty = ul(dirty_product=True)
        self.assertEqual(_ul_dirty_history_count(clean), 0)
        self.assertEqual(_ul_dirty_history_count(dirty), 1)

    def test_traceability_pooler_uses_oldest_clean_unwashed_first(self):
        old_clean, new_clean, dirty = ul(9), ul(2), ul(7, True)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class PoolerHarness:
            _take_uls = Pooler_Agent._take_uls

        pool = PoolerHarness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [new_clean, dirty, old_clean]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, False, 1)
        self.assertEqual(selected, [old_clean])
        self.assertIn(dirty, pool.unwashed_stock_pool[CrateType.TYPE_1])

    def test_traceability_screening_prioritizes_dirty_backlog(self):
        old_dirty = ul(8, True)
        new_clean = ul(0, False)
        model = SimpleNamespace(
            config=SimulationConfig(TRACEABILITY_ENABLED=True, POOL_SCREENING_CAPACITY=1),
            daily_log={'screening': {
                'arrived_uls': 0, 'screened_uls': 0, 'screened_backlog_uls': 0,
                'bypassed_uls': 0, 'processed_uls': 0,
            }},
            steps=10,
        )
        pool = SimpleNamespace(
            model=model, processing_buffer=[], processing_times={}, processing_lead_time=1,
            order_book=[],
            washed_stock_pool={ct: [] for ct in CrateType},
            unwashed_stock_pool={ct: [] for ct in CrateType},
        )
        pool.unwashed_stock_pool[CrateType.TYPE_1].append(old_dirty)
        Pooler_Agent.screen_uls(pool, [new_clean], 10)
        log = model.daily_log['screening']
        self.assertIn(old_dirty, pool.processing_buffer)
        self.assertIn(new_clean, pool.unwashed_stock_pool[CrateType.TYPE_1])
        self.assertEqual(log['screened_backlog_uls'], 1)
        self.assertEqual(log['screened_uls'], 0)
        self.assertEqual(log['bypassed_uls'], 1)

    def test_producer_oldest_first(self):
        old, new = rti(7), rti(1)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        producer = SimpleNamespace(model=model, forward_stock_pro={CrateType.TYPE_1: [new, old]})
        selected = Producer_Agent.extract_rtis(producer, 1, CrateType.TYPE_1)
        self.assertEqual(selected, [old])

    def test_departure_records_node_detention_and_resets_timer(self):
        fake = SimpleNamespace(
            model=SimpleNamespace(
                steps=12,
                daily_log={'detention': {'pro': {'total_days': 0, 'departures': 0}}},
            ),
            location=LocationType.PRO,
            arrival_step=5,
            detention_time=7,
        )
        RTI_Agent.move_to_transport(fake)
        self.assertEqual(fake.model.daily_log['detention']['pro']['total_days'], 7)
        self.assertEqual(fake.model.daily_log['detention']['pro']['departures'], 1)
        self.assertEqual(fake.arrival_step, 12)
        self.assertEqual(fake.location, LocationType.TRANSPORT)

    def test_traceability_falls_back_to_dirty_unwashed_on_flexible_order(self):
        clean, dirty, washed = ul(3), ul(8, True), ul(5)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class Harness:
            _take_uls = Pooler_Agent._take_uls
        pool = Harness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [dirty, clean]
        pool.washed_stock_pool[CrateType.TYPE_1] = [washed]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, False, 2)
        self.assertEqual(selected, [clean, dirty])
        self.assertEqual(pool.washed_stock_pool[CrateType.TYPE_1], [washed])

    def test_traceability_washed_only_still_excludes_dirty_unwashed(self):
        dirty, washed = ul(8, True), ul(1)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class Harness:
            _take_uls = Pooler_Agent._take_uls
        pool = Harness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.washed_stock_pool[CrateType.TYPE_1] = [washed]
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [dirty]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, True, 2)
        self.assertEqual(selected, [washed])
        self.assertEqual(pool.unwashed_stock_pool[CrateType.TYPE_1], [dirty])


if __name__ == '__main__':
    unittest.main()
