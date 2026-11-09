"""Validate screening activity by crate type in a full Task 1 v3 workbook.

Usage:
    python analysis/summarize_screening_by_type.py path/to/sim_log_....xlsx
"""
import argparse
from pathlib import Path
import pandas as pd

FIELDS = ('arrived_uls', 'screened_new_uls', 'screened_backlog_uls',
          'bypassed_uls', 'processed_uls')


def summarize(workbook):
    workbook = Path(workbook)
    raw = pd.read_excel(workbook, sheet_name='ScreeningByType')
    screening = pd.read_excel(workbook, sheet_name='Screening')
    type_data = raw[raw.Step > 0]
    day_data = screening[screening.Step > 0]
    if len(day_data) != 365:
        raise ValueError(f'Expected 365 operating days, got {len(day_data)}')
    wide = type_data.pivot_table(index=['Step', 'Crate Type'], columns='Metric',
                                 values='ULs', aggfunc='sum', fill_value=0).reset_index()
    missing = set(FIELDS).difference(wide.columns)
    if missing:
        raise ValueError('Missing screening-type metrics: ' + ', '.join(sorted(missing)))
    check_map = {
        'arrived_uls': 'arrived_uls',
        'screened_new_uls': 'screened_uls',
        'screened_backlog_uls': 'screened_backlog_uls',
        'bypassed_uls': 'bypassed_uls',
        'processed_uls': 'processed_uls',
    }
    daily = wide.groupby('Step')[list(check_map)].sum()
    day = day_data.set_index('Step')
    for field, expected in check_map.items():
        observed = daily[field].reindex(day.index).fillna(0).astype(int)
        if not observed.equals(day[expected].astype(int)):
            mismatch = int((observed != day[expected]).sum())
            raise ValueError(f'{field} does not reconcile with Screening ({mismatch} days)')

    result = wide.groupby('Crate Type')[list(FIELDS)].sum().astype(int)
    result['total_screened_uls'] = (result['screened_new_uls']
                                   + result['screened_backlog_uls'])
    result['arrival_bypass_pct'] = 100 * result['bypassed_uls'] / result['arrived_uls'].replace(0, float('nan'))
    result = result.sort_values('total_screened_uls', ascending=False)
    print('Per-type screening (unit loads; each UL is 200 RTIs):')
    print(result.to_string(float_format=lambda v: f'{v:.1f}'))
    print('\nAll per-type daily totals match the Screening worksheet: PASS')
    out = workbook.parent / 'screening_by_type_summary.csv'
    result.to_csv(out)
    print('Saved:', out)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook')
    args = parser.parse_args()
    summarize(args.workbook)
