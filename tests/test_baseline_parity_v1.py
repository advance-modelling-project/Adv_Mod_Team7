"""Check exact professor baseline sampling and RNG consumption in the modular Pooler.

Runs quickly; does not require a 365-day simulation.
"""
import random
import unittest
from types import SimpleNamespace

from agents import Pooler_Agent
from config import CrateType, SimulationConfig


def professor_reference(washed, unwashed, needs_washed, quantity):
    """Independent short reproduction of the professor's original logic."""
    if needs_washed is True:
        primary, secondary = washed, []
    else:
        primary, secondary = unwashed, washed
    primary_available = len(primary)
    secondary_available = len(secondary)
    total_available = primary_available + secondary_available
    selected = []
    if total_available >= quantity:
        if primary_available >= quantity:
            selected = random.sample(primary, quantity)
            for item in selected:
                primary.remove(item)
        else:
            first = list(primary)
            primary.clear()
            other = random.sample(secondary, quantity - primary_available)
            for item in other:
                secondary.remove(item)
            selected = first + other
    else:
        selected = list(primary) + list(secondary)
        primary.clear()
        if secondary:
            secondary.clear()
    return selected


class ProfessorBaselineSamplingTests(unittest.TestCase):
    def case(self, washed_count, unwashed_count, quantity, wash_required, seed):
        ct = CrateType.TYPE_1
        ws0 = [('w', i) for i in range(washed_count)]
        us0 = [('u', i) for i in range(unwashed_count)]
        random.seed(seed)
        ws1, us1 = ws0.copy(), us0.copy()
        expected = professor_reference(ws1, us1, wash_required, quantity)
        expected_rng = random.getstate()

        random.seed(seed)
        class Harness:
            _assignment_baseline_extract_uls = Pooler_Agent._assignment_baseline_extract_uls
        pool = Harness()
        pool.model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=False))
        pool.washed_stock_pool = {crate: [] for crate in CrateType}
        pool.unwashed_stock_pool = {crate: [] for crate in CrateType}
        pool.washed_stock_pool[ct] = ws0.copy()
        pool.unwashed_stock_pool[ct] = us0.copy()
        actual = Pooler_Agent.extract_uls(pool, ct, wash_required, quantity)
        self.assertEqual(actual, expected)
        self.assertEqual(pool.washed_stock_pool[ct], ws1)
        self.assertEqual(pool.unwashed_stock_pool[ct], us1)
        self.assertEqual(random.getstate(), expected_rng,
                         'Baseline must consume exactly the same RNG as the professor code')

    def test_washed_only_enough(self):
        self.case(12, 8, 5, True, 42)

    def test_washed_only_short(self):
        self.case(3, 8, 5, True, 43)

    def test_flexible_primary_enough(self):
        self.case(12, 8, 5, False, 44)

    def test_flexible_fallback(self):
        self.case(12, 3, 5, False, 45)

    def test_flexible_stock_exhausted(self):
        self.case(2, 3, 8, False, 46)

    def test_flexible_exact_total(self):
        self.case(2, 3, 5, False, 47)

    def test_flexible_primary_exact(self):
        self.case(3, 5, 5, False, 48)


if __name__ == '__main__':
    unittest.main()
