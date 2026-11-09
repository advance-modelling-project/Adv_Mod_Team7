"""Compare corrected baseline and RFID traceability runs using explicit workbook paths.

Run from repository root:
  python analysis/compare_task1_scenarios.py "run_baseline_.../sim_log_....xlsx" "run_traceability_.../sim_log_....xlsx"

Reads Screening, Fulfillment, Detention, Flows and Stock sheets.
Outputs analysis/reports/task1_comparison.csv and .md.
This reports a descriptive one-seed comparison, NOT a causal/statistical result.
"""
import argparse
from pathlib import Path
import math
import pandas as pd


def screening_summary(df: pd.DataFrame) -> dict:
    required = {'Step', 'arrived_uls', 'screened_uls', 'screened_backlog_uls',
                'bypassed_uls', 'processed_uls', 'capacity_uls'}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f'Screening columns missing: {sorted(missing)}')
    working = df.loc[df['Step'] > 0].copy()
    if len(working) != 365:
        raise ValueError(f'Expected 365 operating days, found {len(working)}')
    admitted = working['screened_uls'] + working['screened_backlog_uls']
    if not (working['arrived_uls'] == working['screened_uls'] + working['bypassed_uls']).all():
        raise ValueError('Arrival accounting failed')
    if not (admitted <= working['capacity_uls']).all():
        raise ValueError('Screening capacity exceeded')
    if not (working[list(required - {'Step'})] >= 0).all().all():
        raise ValueError('Negative screening count')
    arrivals = int(working.arrived_uls.sum())
    capacity = int(working.capacity_uls.sum())
    return {
        'screen_arrivals_uls': arrivals,
        'screen_new_uls': int(working.screened_uls.sum()),
        'screen_backlog_uls': int(working.screened_backlog_uls.sum()),
        'screen_total_uls': int(admitted.sum()),
        'screen_bypassed_uls': int(working.bypassed_uls.sum()),
        'screen_completed_uls': int(working.processed_uls.sum()),
        'screen_utilization_pct': 100 * admitted.sum() / capacity if capacity else float('nan'),
        'screen_bypass_pct': 100 * working.bypassed_uls.sum() / arrivals if arrivals else float('nan'),
        'screen_full_days': int((admitted == working.capacity_uls).sum()),
    }


def summarize(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    screening = pd.read_excel(path, sheet_name='Screening')
    fulfill = pd.read_excel(path, sheet_name='Fulfillment')
    detention = pd.read_excel(path, sheet_name='Detention')
    flows = pd.read_excel(path, sheet_name='Flows')
    stock = pd.read_excel(path, sheet_name='Stock')
    result = screening_summary(screening)
    last = fulfill.loc[fulfill.Step.idxmax()]
    for stream in ('producer', 'pooler'):
        keys = ['created_rtis', 'due_rtis', 'on_time_rtis', 'late_rtis',
                'outstanding_due_rtis', 'not_yet_due_rtis', 'on_time_fill_rate_pct']
        for key in keys:
            value = last[f'{stream}_{key}']
            result[f'{stream}_{key}'] = float(value) if key.endswith('_pct') else int(value)
        if result[f'{stream}_created_rtis'] != sum(result[f'{stream}_{x}'] for x in
              ('on_time_rtis','late_rtis','outstanding_due_rtis','not_yet_due_rtis')):
            raise ValueError(f'{stream}: fulfillment mass balance mismatch')

    for node in ('pool','pro','r_dc','r_pos'):
        daily = detention.loc[detention.Step > 0]
        d = float(daily[f'{node}_total_days'].sum())
        n = int(daily[f'{node}_departures'].sum())
        result[f'detention_{node}_completed_mean_days'] = d / n if n else float('nan')
        result[f'detention_{node}_departures_rtis'] = n

    returned = int(flows.loc[(flows.Origin == 'RDC') & (flows.Destination == 'POOL'), 'Quantity'].sum())
    sent = int(flows.loc[(flows.Origin == 'POOL') & flows.Destination.astype(str).str.startswith('PRO_'), 'Quantity'].sum())
    result['flow_rdc_pool_rtis'] = returned
    result['flow_pool_pro_rtis'] = sent
    result['return_to_dispatch_pct'] = (100*returned/sent if sent else float('nan'))
    stock_daily = stock.loc[stock.Step > 0].groupby(['Step','Warehouse'])['Quantity'].sum().unstack(fill_value=0)
    for key in ('POOL_WASHED','POOL_UNWASHED','POOL_BUFFER'):
        if key in stock_daily.columns:
            result[f'stock_{key.lower()}_average_rtis'] = float(stock_daily[key].mean())
            result[f'stock_{key.lower()}_last_rtis'] = int(stock_daily[key].iloc[-1])
    return result


UNITS = {
    'screen_arrivals_uls':'ULs','screen_new_uls':'ULs','screen_backlog_uls':'ULs',
    'screen_total_uls':'ULs','screen_bypassed_uls':'ULs','screen_completed_uls':'ULs',
    'screen_utilization_pct':'percentage points','screen_bypass_pct':'percentage points',
    'screen_full_days':'days','return_to_dispatch_pct':'percentage points',
}


def unit_for(key):
    if key in UNITS:
        return UNITS[key]
    if key.endswith('_rtis'):
        return 'RTIs'
    if key.endswith('_days'):
        return 'days'
    if key.endswith('_pct'):
        return 'percentage points'
    return 'count'


def display(value, unit):
    return f'{value:,.2f}' if unit in ('percentage points','days') or isinstance(value,float) else f'{value:,}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('traceability',type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path('analysis/reports'))
    args=parser.parse_args()
    baseline=summarize(args.baseline)
    trace=summarize(args.traceability)
    if set(baseline) != set(trace):
        raise ValueError('Scenario metrics differ: verify consistent model versions')
    rows=[]
    for key,b in baseline.items():
        t=trace[key]; d=t-b
        rows.append(dict(Metric=key, Unit=unit_for(key), Baseline=b, Traceability=t, Delta=d))
    results=pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    csv_path=args.output_dir/'task1_comparison.csv'
    report_path=args.output_dir/'task1_comparison.md'
    results.to_csv(csv_path,index=False)
    priority=['producer_on_time_fill_rate_pct','pooler_on_time_fill_rate_pct',
              'producer_outstanding_due_rtis','pooler_outstanding_due_rtis',
              'screen_arrivals_uls','screen_total_uls','screen_backlog_uls',
              'screen_utilization_pct','screen_bypass_pct','screen_full_days',
              'stock_pool_unwashed_average_rtis','stock_pool_washed_average_rtis',
              'flow_pool_pro_rtis','flow_rdc_pool_rtis',
              'detention_pool_completed_mean_days','detention_pro_completed_mean_days',
              'detention_r_dc_completed_mean_days','detention_r_pos_completed_mean_days']
    lines=['# Team 7 — Task 1 baseline versus RFID (one seed)', '',
           f'Baseline workbook: `{args.baseline}`',
           f'Traceability workbook: `{args.traceability}`','',
           'This is a descriptive comparison, **not** a statistically supported improvement claim.',
           'Same seed controls repeatability within each configuration, but policies may consume random draws differently.',
           'Differences in delivery volumes can therefore reflect both policy and differing stochastic trajectories.','',
           '| KPI | Baseline | Traceability | Difference | Units |',
           '|---|---:|---:|---:|---|']
    for key in priority:
        if key not in baseline: continue
        unit=unit_for(key)
        lines.append(f'| {key} | {display(baseline[key],unit)} | {display(trace[key],unit)} | {display(trace[key]-baseline[key],unit)} | {unit} |')
    lines+=['', '## Interpretation cautions','',
            '- Screening **operations** include both new arrivals and previously bypassed backlog ULs.',
            '- Full capacity days must use new + backlog screening, not new arrivals only.',
            '- Order fill rate is delivered-on-time RTIs / due RTIs (not the fraction of order lines fully satisfied).',
            '- Average detention here covers **completed stays** only; unresolved stock is right-censored.',
            '- Return-to-dispatch is an aggregate flow ratio, not a reuse probability.',
            '- An RFID scenario cannot be called better solely because utilization is high; service and circularity must also be assessed.',
            '', '## Decision gate', '',
            'Do not merge a traceability policy solely based on passing unit tests. Verify that both full-year runs complete, all accounting checks pass, and the proposed rules have acceptable service-level consequences.',
            'For Task 2, run multiple independent seeds and report uncertainty.', '']
    report_path.write_text('\n'.join(lines),encoding='utf-8')
    print('\nCRITICAL TASK 1 METRICS — baseline vs traceability')
    for key in priority:
        if key not in baseline:continue
        unit=unit_for(key)
        print(f'{key:46} {display(baseline[key],unit):>14} -> {display(trace[key],unit):>14} (delta {display(trace[key]-baseline[key],unit)})')
    print(f'\nReports: {csv_path.resolve()}\n         {report_path.resolve()}')


if __name__=='__main__':
    main()
