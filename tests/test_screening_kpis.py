"""Tests for Team 7 screening KPI instrumentation.

Run from repository root using the stdlib unittest runner:
    python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from agents import Pooler_Agent
from config import CrateType, SimulationConfig, UnitLoad
from model import CLSC_Model


def empty_log():
    return dict(arrived_uls=0, screened_uls=0, bypassed_uls=0, processed_uls=0)


class ScreeningMetricsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = SimulationConfig(POOL_SCREENING_CAPACITY=2)
        self.model = SimpleNamespace(
            config=self.cfg,
            daily_log={'screening': empty_log()},
        )
        self.pool = SimpleNamespace(
            model=self.model,
            processing_buffer=[],
            processing_times={},
            processing_lead_time=1,
            washed_stock_pool={ct: [] for ct in CrateType},
            unwashed_stock_pool={ct: [] for ct in CrateType},
        )
        self.pool.process_rti = lambda rti: setattr(rti, 'washed', True)

    def loads(self, number):
        return [UnitLoad(CrateType.TYPE_1, [SimpleNamespace(under_processing=False, washed=False)])
                for _ in range(number)]

    def test_admits_at_most_capacity_and_counts_bypass(self):
        Pooler_Agent.screen_uls(self.pool, self.loads(5), 10)
        counters = self.model.daily_log['screening']
        self.assertEqual(counters['arrived_uls'], 5)
        self.assertEqual(counters['screened_uls'], 2)
        self.assertEqual(counters['bypassed_uls'], 3)
        self.assertEqual(len(self.pool.processing_buffer), 2)
        self.assertEqual(len(self.pool.unwashed_stock_pool[CrateType.TYPE_1]), 3)
        self.assertTrue(all(rti.under_processing for ul in self.pool.processing_buffer for rti in ul.rtis))

    def test_processing_is_recorded_separately(self):
        Pooler_Agent.screen_uls(self.pool, self.loads(3), 10)
        self.model.steps = 11
        Pooler_Agent.process_uls(self.pool)
        counters = self.model.daily_log['screening']
        self.assertEqual(counters['processed_uls'], 2)
        self.assertEqual(len(self.pool.washed_stock_pool[CrateType.TYPE_1]), 2)
        self.assertEqual(len(self.pool.processing_buffer), 0)

    def test_zero_capacity_counts_bypass(self):
        self.model.config.POOL_SCREENING_CAPACITY = 0
        Pooler_Agent.screen_uls(self.pool, self.loads(3), 10)
        self.assertEqual(self.model.daily_log['screening']['screened_uls'], 0)
        self.assertEqual(self.model.daily_log['screening']['bypassed_uls'], 3)

    def test_export_creates_screening_tab(self):
        # Check actual exporter without constructing 322,800 RTI agents.
        columns = {
            'Stock|POOL_WASHED|TYPE_1': [200, 200],
            'Flow|RDC|POOL|TYPE_1': [0, 1000],
            'Backorders|POOL_WASHED|TYPE_1': [0, 0],
            'Screening|arrived_uls': [0, 5],
            'Screening|screened_uls': [0, 2],
            'Screening|bypassed_uls': [0, 3],
            'Screening|processed_uls': [0, 1],
            'Screening|capacity_uls': [2, 2],
            'Screening|utilization_pct': [0.0, 100.0],
            'Screening|bypass_rate_pct': [None, 60.0],
        }
        data = pd.DataFrame(columns)
        with tempfile.TemporaryDirectory() as directory:
            fake_model = SimpleNamespace(
                results_dir=directory, timestamp='test', all_orders=[],
                datacollector=SimpleNamespace(get_model_vars_dataframe=lambda: data),
            )
            CLSC_Model.export_to_excel(fake_model)
            workbook = Path(directory) / 'sim_log_test.xlsx'
            self.assertTrue(workbook.exists())
            with pd.ExcelFile(workbook) as excel:
                sheets = excel.sheet_names
                self.assertIn('Screening', sheets)
                self.assertTrue({'Stock', 'Flows', 'Backorders'}.issubset(sheets))
                rows = pd.read_excel(excel, sheet_name='Screening')
            self.assertEqual(rows['screened_uls'].iloc[1], 2)
            self.assertEqual(rows['bypassed_uls'].iloc[1], 3)
            self.assertEqual(rows['utilization_pct'].iloc[1], 100)
            self.assertEqual(rows['bypass_rate_pct'].iloc[1], 60)


if __name__ == '__main__':
    unittest.main()
