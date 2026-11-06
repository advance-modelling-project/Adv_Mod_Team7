"""Reconcile and summarize the newest Team 7 order-fulfillment workbook.

From repository root: python analysis/summarize_fulfillment.py
"""
from pathlib import Path
import pandas as pd


def main():
    files = list(Path.cwd().glob('run_*/sim_log_*.xlsx'))
    if not files:
        raise SystemExit('No run workbook found; run python main.py first.')
    workbook = max(files, key=lambda p: p.stat().st_mtime)
    daily = pd.read_excel(workbook, sheet_name='Fulfillment')
    audit = pd.read_excel(workbook, sheet_name='OrderAudit')
    if daily.empty or audit.empty:
        raise SystemExit('Missing fulfillment data; check instrumentation.')

    balance = audit['Original RTIs'] == (audit['On Time RTIs'] + audit['Late RTIs'] + audit['Outstanding RTIs'])
    print(f'Workbook: {workbook}')
    print(f'Order audit rows: {len(audit):,}')
    print(f'Every order balances: {"PASS" if balance.all() else "FAIL"}')
    if not balance.all():
        raise SystemExit('Order-level reconciliation failed!')

    end = daily.loc[daily.Step.idxmax()]
    for prefix, heading in [('producer', 'RDC orders fulfilled by producers'),
                            ('pooler', 'Producer orders fulfilled by pooler')]:
        due = int(end[f'{prefix}_due_rtis'])
        created = int(end[f'{prefix}_created_rtis'])
        timely = int(end[f'{prefix}_on_time_rtis'])
        late = int(end[f'{prefix}_late_rtis'])
        overdue = int(end[f'{prefix}_outstanding_due_rtis'])
        future = int(end[f'{prefix}_not_yet_due_rtis'])
        rate = end[f'{prefix}_on_time_fill_rate_pct']
        print(f'\n{heading}:')
        print(f'  Created: {created:,} RTIs; due by horizon: {due:,} RTIs')
        print(f'  On time: {timely:,}; late: {late:,}; outstanding due: {overdue:,}; not yet due: {future:,}')
        print(f'  On-time quantity fill rate: {rate:.2f}%' if pd.notna(rate) else '  On-time fill rate: not defined (no orders due)')
        print(f'  Mass balance: {"PASS" if created == timely + late + overdue + future else "FAIL"}')
        if created != timely + late + overdue + future:
            raise SystemExit('Fulfillment aggregate balance failed.')

    print('\nNote: these are delivered quantities, not a cost, lateness-duration, or unique-crate metric.')


if __name__ == '__main__':
    main()
