"""Summarize RFID traceability KPIs from a simulation workbook.

Usage:
    python analysis/summarize_traceability.py path/to/sim_log.xlsx
"""
import argparse
from pathlib import Path
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', nargs='?', type=Path)
    args = parser.parse_args()
    if args.workbook:
        workbook = args.workbook
    else:
        files = list(Path.cwd().glob('run_*/sim_log_*.xlsx'))
        if not files:
            raise SystemExit('No workbook found. Run main.py first.')
        workbook = max(files, key=lambda p: p.stat().st_mtime)

    detention = pd.read_excel(workbook, sheet_name='Detention')
    screening = pd.read_excel(workbook, sheet_name='Screening')
    fulfillment = pd.read_excel(workbook, sheet_name='Fulfillment')
    flows = pd.read_excel(workbook, sheet_name='Flows')

    operating = detention.loc[detention.Step > 0]
    print(f'Workbook: {workbook}')
    print('\nAverage completed detention time by node:')
    for node in ('pool', 'pro', 'r_dc', 'r_pos'):
        days = pd.to_numeric(operating[f'{node}_total_days'], errors='coerce').fillna(0).sum()
        departures = pd.to_numeric(operating[f'{node}_departures'], errors='coerce').fillna(0).sum()
        average = days / departures if departures else float('nan')
        print(f'  {node}: {average:.2f} days ({int(departures):,} RTI departures)')

    operating_screen = screening.loc[screening.Step > 0]
    arrived = int(operating_screen.arrived_uls.sum())
    screened_new = int(operating_screen.screened_uls.sum())
    screened_backlog = int(operating_screen.screened_backlog_uls.sum())
    bypassed = int(operating_screen.bypassed_uls.sum())
    capacity = int(operating_screen.capacity_uls.sum())
    total_screened = screened_new + screened_backlog
    print('\nPooler screening:')
    print(f'  Arrivals: {arrived:,} ULs')
    print(f'  New arrivals screened: {screened_new:,} ULs')
    print(f'  Dirty backlog re-screened: {screened_backlog:,} ULs')
    print(f'  Bypassed on arrival: {bypassed:,} ULs')
    print(f'  Capacity utilization: {100 * total_screened / capacity:.1f}%' if capacity else '  Capacity utilization: n/a')
    print(f'  Arrival bypass rate: {100 * bypassed / arrived:.1f}%' if arrived else '  Arrival bypass rate: n/a')

    last = fulfillment.loc[fulfillment.Step.idxmax()]
    print('\nOn-time order quantity fill rates:')
    print(f"  Producers -> RDC: {last['producer_on_time_fill_rate_pct']:.2f}%")
    print(f"  Pooler -> producers: {last['pooler_on_time_fill_rate_pct']:.2f}%")

    pool_to_pro = flows.loc[(flows.Origin == 'POOL') & flows.Destination.astype(str).str.startswith('PRO_'), 'Quantity'].sum()
    rdc_to_pool = flows.loc[(flows.Origin == 'RDC') & (flows.Destination == 'POOL'), 'Quantity'].sum()
    ratio = 100 * rdc_to_pool / pool_to_pro if pool_to_pro else float('nan')
    print('\nReverse-loop throughput indicator:')
    print(f'  RTIs returned RDC -> POOL: {int(rdc_to_pool):,}')
    print(f'  RTIs dispatched POOL -> PRO: {int(pool_to_pro):,}')
    print(f'  Return-to-dispatch ratio: {ratio:.2f}%')
    print('  Caution: this is an aggregate horizon flow ratio, not a cohort-based reuse probability.')


if __name__ == '__main__':
    main()
