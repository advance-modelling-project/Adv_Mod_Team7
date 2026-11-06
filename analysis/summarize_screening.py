"""Validate and summarize the newest Team 7 Screening sheet.

Usage from repository root:
    python analysis/summarize_screening.py
"""
from pathlib import Path
import pandas as pd


def main():
    files = list(Path.cwd().glob('run_*/sim_log_*.xlsx'))
    if not files:
        raise SystemExit('No simulation workbook found. Run python main.py first.')
    latest = max(files, key=lambda p: p.stat().st_mtime)
    df = pd.read_excel(latest, sheet_name='Screening')
    expected = {'Step', 'arrived_uls', 'screened_uls', 'bypassed_uls',
                'processed_uls', 'capacity_uls', 'utilization_pct', 'bypass_rate_pct'}
    if not expected.issubset(df.columns):
        raise SystemExit(f'Missing columns: {sorted(expected - set(df.columns))}')

    # Mesa exports an initial snapshot at Step 0; this is not a working day.
    df = df[df['Step'] > 0].copy()
    if df.empty:
        raise SystemExit('No simulated operating days found.')

    checks = {
        'arrivals = screened + bypassed': bool((df.arrived_uls == df.screened_uls + df.bypassed_uls).all()),
        'screened <= daily capacity': bool((df.screened_uls <= df.capacity_uls).all()),
        'counts are nonnegative': bool((df[['arrived_uls', 'screened_uls', 'bypassed_uls', 'processed_uls']] >= 0).all().all()),
    }
    print(f'Workbook: {latest}')
    print(f'Operating days: {len(df)}')
    for name, passed in checks.items():
        print(f'  {name}: {"PASS" if passed else "FAIL"}')

    arrived = int(df.arrived_uls.sum())
    screened = int(df.screened_uls.sum())
    bypassed = int(df.bypassed_uls.sum())
    completed = int(df.processed_uls.sum())
    all_capacity = int(df.capacity_uls.sum())
    util = 100 * screened / all_capacity if all_capacity > 0 else float('nan')
    bypass = 100 * bypassed / arrived if arrived > 0 else float('nan')

    print(f'Total arriving ULs: {arrived:,}')
    print(f'Admitted to screening: {screened:,} ULs')
    print(f'Bypassed screening: {bypassed:,} ULs')
    print(f'Completed recovery: {completed:,} ULs')
    print(f'Overall screening capacity utilization: {util:.1f}%')
    print(f'Overall bypass rate: {bypass:.1f}%')
    print(f'Days at full screening capacity: {int((df.screened_uls == df.capacity_uls).sum())} / {len(df)}')

    if not all(checks.values()):
        raise SystemExit('KPI consistency checks FAILED; investigate before interpreting results.')


if __name__ == '__main__':
    main()
