"""Audit the RDC order/producer shipment gap in Team 7's baseline simulation.

From the Adv_Mod_Team7 repository root, run:
    python analysis/check_order_gap.py

Optionally select a particular workbook:
    python analysis/check_order_gap.py 'run_2026.11.06_13.42/sim_log_2026.11.06_13.42.xlsx'

Creates run_.../baseline_diagnostics/order_gap_audit.md.
This audit reconciles aggregate quantities, NOT individual on-time fulfillment.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def find_latest_workbook() -> Path:
    paths = list(Path('.').glob('run_*/sim_log_*.xlsx'))
    if not paths:
        raise FileNotFoundError('No simulation workbook found under run_*/. Run python main.py first.')
    return max(paths, key=lambda p: p.stat().st_mtime)


def audit(orders: pd.DataFrame, flows: pd.DataFrame, last_step: int) -> dict:
    required_orders = {'Step', 'Issuer', 'UoM', 'Lead Time', 'Quantity'}
    required_flows = {'Step', 'Origin', 'Destination', 'Quantity'}
    if missing := required_orders - set(orders.columns):
        raise ValueError(f'Orders sheet missing columns: {sorted(missing)}')
    if missing := required_flows - set(flows.columns):
        raise ValueError(f'Flows sheet missing columns: {sorted(missing)}')

    # RDC-issued orders are in individual RTIs. Producer-to-RDC flows are also RTIs.
    rdc = orders.loc[orders['Issuer'].eq('RDC_1') & orders['UoM'].eq('RTI')].copy()
    for col in ('Step', 'Lead Time', 'Quantity'):
        rdc[col] = pd.to_numeric(rdc[col], errors='raise').astype('int64')
    if ((rdc['Quantity'] < 0) | (rdc['Lead Time'] < 0)).any():
        raise ValueError('Negative quantity or lead time in RDC orders.')
    rdc['Due Step'] = rdc['Step'] + rdc['Lead Time']
    due = rdc.loc[rdc['Due Step'] <= last_step]
    not_yet_due = rdc.loc[rdc['Due Step'] > last_step]

    flow_mask = (flows['Origin'].astype(str).str.startswith('PRO_') &
                 flows['Destination'].eq('RDC') &
                 pd.to_numeric(flows['Step']).between(1, last_step))
    dispatched = int(pd.to_numeric(flows.loc[flow_mask, 'Quantity'], errors='raise').sum())
    total_ordered = int(rdc['Quantity'].sum())
    due_qty = int(due['Quantity'].sum())
    future_qty = int(not_yet_due['Quantity'].sum())
    result = {
        'last_step': last_step,
        'orders_total': len(rdc),
        'ordered_rtis': total_ordered,
        'due_order_rtis': due_qty,
        'not_yet_due_rtis': future_qty,
        'shipped_rtis': dispatched,
        'all_orders_minus_shipments': total_ordered - dispatched,
        'due_orders_minus_shipments': due_qty - dispatched,
        'horizon_explains_gap': total_ordered - dispatched == future_qty,
        'future_breakdown': (not_yet_due.groupby(['Step', 'Lead Time', 'Due Step'],
                                                 as_index=False)['Quantity'].sum()
                             .sort_values(['Step', 'Lead Time'])),
    }
    return result


def format_report(result: dict, workbook: Path) -> str:
    s = result
    lines = [
        '# Team 7 - order horizon reconciliation', '',
        f'Source: `{workbook}`', '',
        '## Aggregate quantities', '',
        '| Quantity | RTIs |', '|---|---:|',
        f"| Total RDC-issued demand | {s['ordered_rtis']:,} |",
        f"| RDC orders due by day {s['last_step']} | {s['due_order_rtis']:,} |",
        f"| RDC orders not yet due by day {s['last_step']} | {s['not_yet_due_rtis']:,} |",
        f"| Producer-to-RDC shipments through day {s['last_step']} | {s['shipped_rtis']:,} |",
        f"| Total ordered minus shipped | {s['all_orders_minus_shipments']:,} |",
        f"| Due orders minus shipped (aggregate only) | {s['due_orders_minus_shipments']:,} |",
        '',
        f"**Does not-yet-due demand exactly explain the observed gap? {s['horizon_explains_gap']}**", '',
        '## Interpretation', '',
        ('The observed aggregate gap is fully explained by orders whose due dates lie after the simulation horizon.'
         if s['horizon_explains_gap'] else
         'Not-yet-due orders do not fully explain the gap. Investigate overdue orders, end-of-run stock, and shipment accounting.'),
        '',
        '**Caution:** This is not an on-time fill-rate calculation. The exported Orders sheet '
        'records created orders but does not link shipments to order IDs or record actual fulfillment times.',
        '', '## Orders with due dates after the horizon', '',
        '| Created on day | Lead time (days) | Due on day | Quantity (RTIs) |',
        '|---:|---:|---:|---:|',
    ]
    df = s['future_breakdown']
    if df.empty:
        lines.append('| - | - | - | 0 |')
    else:
        for row in df.itertuples(index=False, name=None):
            lines.append(f'| {row[0]} | {row[1]} | {row[2]} | {int(row[3]):,} |')
    lines.extend(['', '## What the model must record next', '',
                  'For rigorous KPI measurement, log each order ID, due day, fulfilled quantity, '
                  'actual dispatch day, and any remaining quantity after due date.', ''])
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', nargs='?', type=Path)
    args = parser.parse_args()
    path = args.workbook or find_latest_workbook()
    if not path.is_file():
        raise FileNotFoundError(path)
    orders = pd.read_excel(path, sheet_name='Orders')
    flows = pd.read_excel(path, sheet_name='Flows')
    stock = pd.read_excel(path, sheet_name='Stock', usecols=['Step'])
    last_step = int(pd.to_numeric(stock['Step']).max())
    result = audit(orders, flows, last_step)
    outdir = path.parent / 'baseline_diagnostics'
    outdir.mkdir(parents=True, exist_ok=True)
    output = outdir / 'order_gap_audit.md'
    output.write_text(format_report(result, path), encoding='utf-8')
    print(f"Ordered: {result['ordered_rtis']:,} RTIs")
    print(f"Shipped: {result['shipped_rtis']:,} RTIs")
    print(f"Not yet due: {result['not_yet_due_rtis']:,} RTIs")
    print(f"Unexplained aggregate due-vs-shipped difference: {result['due_orders_minus_shipments']:,} RTIs")
    print(f"End-of-horizon explanation matches exactly: {result['horizon_explains_gap']}")
    print(f'Audit report: {output.resolve()}')


if __name__ == '__main__':
    main()
