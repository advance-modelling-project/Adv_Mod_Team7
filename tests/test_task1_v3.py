"""Shortage-aware RFID screening selection tests (measurement and behavior)."""
import unittest
from types import SimpleNamespace
from agents import select_shortage_aware_uls
from config import CrateType


def fake_ul(type_, number, dirty_count=0, dwell=0):
    # In the real simulation ULs contain RTIs; this lightweight fixture keeps
    # just enough RFID data for product history and average detention.
    product = SimpleNamespace(makes_dirty=True)
    rtis = [SimpleNamespace(product=product if i < dirty_count else None,
                            detention_time=dwell) for i in range(4)]
    return SimpleNamespace(crate_type=type_, rtis=rtis, id=f'{type_.name}_{number}')


class RecoveryPriorityTests(unittest.TestCase):
    def test_washed_shortage_beats_dirty_history_on_other_type(self):
        dirty_t1 = fake_ul(CrateType.TYPE_1, 1, dirty_count=4, dwell=30)
        clean_t4 = fake_ul(CrateType.TYPE_4, 2, dirty_count=0, dwell=1)
        selected = select_shortage_aware_uls(
            [dirty_t1, clean_t4], {CrateType.TYPE_4: 1}, 1
        )
        self.assertEqual([u.id for u in selected], [clean_t4.id])

    def test_balances_equal_shortages_across_types(self):
        items = ([fake_ul(CrateType.TYPE_1, i) for i in range(4)]
                 + [fake_ul(CrateType.TYPE_4, i) for i in range(4)])
        selected = select_shortage_aware_uls(items, {
            CrateType.TYPE_1: 4, CrateType.TYPE_4: 4,
        }, 4)
        self.assertEqual(len(selected), 4)
        self.assertTrue(any(u.crate_type == CrateType.TYPE_1 for u in selected))
        self.assertTrue(any(u.crate_type == CrateType.TYPE_4 for u in selected))

    def test_no_shortage_uses_dirty_history_then_waiting_time(self):
        clean = fake_ul(CrateType.TYPE_4, 1, dirty_count=0, dwell=100)
        dirty_short = fake_ul(CrateType.TYPE_1, 1, dirty_count=1, dwell=3)
        dirty_old = fake_ul(CrateType.TYPE_1, 2, dirty_count=1, dwell=9)
        selected = select_shortage_aware_uls(
            [clean, dirty_short, dirty_old], {}, 1
        )
        self.assertEqual(selected[0].id, dirty_old.id)

    def test_preserves_input_and_caps_selection(self):
        items = [fake_ul(CrateType.TYPE_4, i, dirty_count=1) for i in range(5)]
        selected = select_shortage_aware_uls(items, {CrateType.TYPE_4: 20}, 2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(len({u.id for u in selected}), 2)
        self.assertEqual(len(items), 5)
        self.assertEqual(select_shortage_aware_uls(items, {}, 0), [])


if __name__ == '__main__':
    unittest.main()
