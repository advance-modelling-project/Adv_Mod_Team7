"""Regression tests for the screening accounting in the Task 1 comparison."""
import unittest
import pandas as pd
from analysis.compare_task1_scenarios import screening_summary


class Task1ReportingTests(unittest.TestCase):
    def test_backlog_counts_toward_full_screening_days(self):
        rows = []
        for day in range(366):
            # One operational day at full capacity: 12 new + 8 backlog.
            # Others have zero arrivals and zero operations.
            rows.append(dict(Step=day, arrived_uls=12 if day==1 else 0,
                             screened_uls=12 if day==1 else 0,
                             screened_backlog_uls=8 if day==1 else 0,
                             bypassed_uls=0, processed_uls=0, capacity_uls=20))
        data = pd.DataFrame(rows)
        summary = screening_summary(data)
        self.assertEqual(summary['screen_full_days'],1)
        self.assertEqual(summary['screen_total_uls'],20)
        self.assertAlmostEqual(summary['screen_utilization_pct'],100*20/(365*20))

    def test_screening_rejects_more_than_capacity(self):
        rows=[dict(Step=day, arrived_uls=12 if day==1 else 0,
                   screened_uls=12 if day==1 else 0, screened_backlog_uls=9 if day==1 else 0,
                   bypassed_uls=0, processed_uls=0, capacity_uls=20) for day in range(366)]
        with self.assertRaises(ValueError):
            screening_summary(pd.DataFrame(rows))


if __name__=='__main__':
    unittest.main()
