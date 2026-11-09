"""Apply measurement-only order KPI instrumentation to the Team 7 current main.

Run once from the root of Adv_Mod_Team7:
    python tools/apply_fulfillment_kpis.py

The script refuses ambiguous/mismatched source files. It does not modify
operational decisions; inspect git diff after running.
"""
from pathlib import Path


def once(contents: str, target: str, replacement: str, location: str) -> str:
    count = contents.count(target)
    if count != 1:
        raise SystemExit(f'Unsafe patch: expected exactly one {location} anchor; found {count}. No files written.')
    return contents.replace(target, replacement, 1)


def main():
    root = Path.cwd()
    agents_file, model_file = root / 'agents.py', root / 'model.py'
    metrics_file = root / 'fulfillment_metrics.py'
    if not all(p.is_file() for p in (agents_file, model_file, metrics_file)):
        raise SystemExit('Run from the repository root after extracting the package.')
    agents = agents_file.read_text(encoding='utf-8')
    model = model_file.read_text(encoding='utf-8')
    if 'order_tracker.register(' in agents or 'Fulfillment|' in model:
        raise SystemExit('Fulfillment instrumentation appears already applied. No files changed.')
    if 'Screening|arrived_uls' not in model:
        raise SystemExit('Expected screening-KPI version of model.py. Pull latest main first.')

    # Register a stable original quantity for each generated pooler and producer order.
    agents = once(agents,
        '                self.model.pool_agent.receive_orders(order)\n',
        '                self.model.pool_agent.receive_orders(order)\n                self.model.order_tracker.register(order)\n',
        'pooler order registration')
    agents = once(agents,
        '            target_producer.receive_orders(order)\n',
        '            target_producer.receive_orders(order)\n            self.model.order_tracker.register(order)\n',
        'producer order registration')

    # Both calls record ACTUAL delivered quantities before mutable order.quantity is reduced.
    agents = once(agents,
        '            shortage_uls = order.quantity - extracted_qty_uls\n',
        '            self.model.order_tracker.deliver(order, extracted_qty_uls, self.model.steps)\n'
        '            shortage_uls = order.quantity - extracted_qty_uls\n',
        'pooler fulfillment')
    agents = once(agents,
        '            shortage = order.quantity - extracted_qty\n',
        '            self.model.order_tracker.deliver(order, extracted_qty, self.model.steps)\n'
        '            shortage = order.quantity - extracted_qty\n',
        'producer fulfillment')

    model = once(model, 'from datetime import datetime\n',
                 'from datetime import datetime\nfrom fulfillment_metrics import OrderTracker\n', 'tracker import')
    model = once(model, '        self.all_orders = []\n',
                 '        self.all_orders = []\n'
                 '        self.order_tracker = OrderTracker(self.config.UL_SIZE)\n'
                 '        self.fulfillment_snapshot = self.order_tracker.snapshot(self.steps)\n',
                 'tracker initialization')
    model = once(model, '        self.datacollector = mesa.DataCollector(model_reporters=reporters)\n',
                 '        # Measurement-only order metrics (all quantities in RTIs).\n'
                 '        for field in self.fulfillment_snapshot:\n'
                 '            reporters[f"Fulfillment|{field}"] = lambda m, key=field: m.fulfillment_snapshot[key]\n\n'
                 '        self.datacollector = mesa.DataCollector(model_reporters=reporters)\n',
                 'reporter registration')
    anchor = '        self.datacollector.collect(self)\n'
    if model.count(anchor) != 2:
        raise SystemExit(f'Unsafe patch: expected two data collection locations, found {model.count(anchor)}.')
    pos = model.rfind(anchor)
    model = model[:pos] + '        self.fulfillment_snapshot = self.order_tracker.snapshot(self.steps)\n' + model[pos:]

    export_anchor = "                screening_df.to_excel(writer, sheet_name='Screening', index=False)\n"
    export_insert = (
        "                screening_df.to_excel(writer, sheet_name='Screening', index=False)\n\n"
        "            fulfillment_cols = [c for c in df_wide.columns if c.startswith('Fulfillment|')]\n"
        "            if fulfillment_cols:\n"
        "                fulfillment_df = df_wide[['Step', *fulfillment_cols]].copy()\n"
        "                fulfillment_df.columns = ['Step'] + [c.split('|', 1)[1] for c in fulfillment_cols]\n"
        "                fulfillment_df.to_excel(writer, sheet_name='Fulfillment', index=False)\n"
        "            tracker = getattr(self, 'order_tracker', None)\n"
        "            if tracker is not None:\n"
        "                pd.DataFrame(tracker.audit_rows(self.steps)).to_excel(writer, sheet_name='OrderAudit', index=False)\n"
    )
    model = once(model, export_anchor, export_insert, 'Excel export')

    # Both source files are validated in memory before either is written.
    compile(agents, str(agents_file), 'exec')
    compile(model, str(model_file), 'exec')
    agents_file.write_text(agents, encoding='utf-8')
    model_file.write_text(model, encoding='utf-8')
    print('Patched agents.py and model.py. Review with: git diff -- agents.py model.py')
    print('New export sheets: Fulfillment and OrderAudit.')


if __name__ == '__main__':
    main()
