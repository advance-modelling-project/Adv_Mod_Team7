"""Repair Team 7 Task 1 RFID policy and screening-report consistency.

Run from the repository root, AFTER the first RFID patch was applied:
    python tools/repair_traceability_v2.py

It changes only RFID-mode Pooler allocation behavior; it keeps baseline
selection and all shipping, recovery and physical capacity constraints intact.
It validates all source anchors before writing any files.
"""
from pathlib import Path

ROOT = Path.cwd()
changes = {}
new_files = {}


def replace_once(path, old, new):
    target = ROOT / path
    original = changes.get(path, target.read_text(encoding='utf-8'))
    count = original.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected exactly one matching block; found {count}. No files written.')
    changes[path] = original.replace(old, new, 1)
    print(f'Validated {path}')


def append_new(path, content):
    if (ROOT / path).exists():
        raise RuntimeError(f'{path} already exists; no files written.')
    new_files[path] = content


OLD_POLICY = """    def extract_uls(self, crate_type: CrateType, needs_washed: Optional[bool], quantity_uls: int) -> List[UnitLoad]:
        washed_stock = self.washed_stock_pool[crate_type]
        unwashed_stock = self.unwashed_stock_pool[crate_type]

        if needs_washed is True:
            return self._take_uls(washed_stock, quantity_uls)

        # RFID rule: do not dispatch unwashed ULs whose product history indicates
        # that their RTIs require washing. Use washed stock as a safe fallback.
        candidates = unwashed_stock
        if self.model.config.TRACEABILITY_ENABLED:
            candidates = [ul for ul in unwashed_stock if _ul_dirty_history_count(ul) == 0]

        selected = self._take_uls(unwashed_stock, quantity_uls, candidates)
        remaining = quantity_uls - len(selected)
        if remaining > 0:
            selected.extend(self._take_uls(washed_stock, remaining))
        return selected
"""

NEW_POLICY = """    def extract_uls(self, crate_type: CrateType, needs_washed: Optional[bool], quantity_uls: int) -> List[UnitLoad]:
        washed_stock = self.washed_stock_pool[crate_type]
        unwashed_stock = self.unwashed_stock_pool[crate_type]

        if needs_washed is True:
            # A strict washed-only order must always receive washed ULs.
            return self._take_uls(washed_stock, quantity_uls)

        if not self.model.config.TRACEABILITY_ENABLED:
            # Preserve the assignment baseline: unwashed first, then washed.
            selected = self._take_uls(unwashed_stock, quantity_uls)
        else:
            # Soft RFID prioritization: prefer clean-history unwashed ULs but
            # do NOT impose a new wash-only constraint on an order whose
            # specification explicitly allows unwashed crates.
            # Using dirty-history ULs as a fallback matches baseline eligibility.
            # This is a model feasibility decision, not a food-safety claim.
            clean = [ul for ul in unwashed_stock if _ul_dirty_history_count(ul) == 0]
            selected = self._take_uls(unwashed_stock, quantity_uls, clean)
            remaining = quantity_uls - len(selected)
            if remaining > 0:
                dirty_history = [ul for ul in unwashed_stock if _ul_dirty_history_count(ul) > 0]
                selected.extend(self._take_uls(unwashed_stock, remaining, dirty_history))

        remaining = quantity_uls - len(selected)
        if remaining > 0:
            selected.extend(self._take_uls(washed_stock, remaining))
        return selected
"""

# Exact block comes from the previously provided Task 1 patch.
replace_once('agents.py', OLD_POLICY, NEW_POLICY)

replace_once(
    'analysis/summarize_screening.py',
    "    print(f'Days at full screening capacity: {int((df.screened_uls == df.capacity_uls).sum())} / {len(df)}')\n",
    "    total_screened_per_day = df.screened_uls + df.screened_backlog_uls\n"
    "    print(f'Days at full screening capacity: {int((total_screened_per_day == df.capacity_uls).sum())} / {len(df)}')\n",
)

replace_once(
    'README_TRACEABILITY.md',
    '3. **Safe unwashed allocation:** orders that do not require washed crates use clean unwashed ULs first; dirty unwashed ULs are held for recovery. Washed stock remains the fallback.\n',
    '3. **Soft RFID stock allocation:** orders requiring washed crates receive washed ULs. Orders without this requirement first select clean-history unwashed ULs, then other unwashed ULs, and finally washed ULs if necessary. This preserves baseline order feasibility; it is not a food-safety claim.\n',
)

# Add two behavioral regression tests in the existing class, but leave original 17 intact.
append_tests = """    def test_traceability_falls_back_to_dirty_unwashed_on_flexible_order(self):
        clean, dirty, washed = ul(3), ul(8, True), ul(5)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class Harness:
            _take_uls = Pooler_Agent._take_uls
        pool = Harness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [dirty, clean]
        pool.washed_stock_pool[CrateType.TYPE_1] = [washed]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, False, 2)
        self.assertEqual(selected, [clean, dirty])
        self.assertEqual(pool.washed_stock_pool[CrateType.TYPE_1], [washed])

    def test_traceability_washed_only_still_excludes_dirty_unwashed(self):
        dirty, washed = ul(8, True), ul(1)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class Harness:
            _take_uls = Pooler_Agent._take_uls
        pool = Harness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.washed_stock_pool[CrateType.TYPE_1] = [washed]
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [dirty]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, True, 2)
        self.assertEqual(selected, [washed])
        self.assertEqual(pool.unwashed_stock_pool[CrateType.TYPE_1], [dirty])

"""
replace_once(
    'tests/test_traceability_policy.py',
    "\n\nif __name__ == '__main__':\n    unittest.main()\n",
    '\n'+append_tests+"\nif __name__ == '__main__':\n    unittest.main()\n",
)

# The full comparison tool is copied in by this patch, not downloaded at runtime.
comparison_text = '"""Compare corrected baseline and RFID traceability runs using explicit workbook paths.\n\nRun from repository root:\n  python analysis/compare_task1_scenarios.py "run_baseline_.../sim_log_....xlsx" "run_traceability_.../sim_log_....xlsx"\n\nReads Screening, Fulfillment, Detention, Flows and Stock sheets.\nOutputs analysis/reports/task1_comparison.csv and .md.\nThis reports a descriptive one-seed comparison, NOT a causal/statistical result.\n"""\nimport argparse\nfrom pathlib import Path\nimport math\nimport pandas as pd\n\n\ndef screening_summary(df: pd.DataFrame) -> dict:\n    required = {\'Step\', \'arrived_uls\', \'screened_uls\', \'screened_backlog_uls\',\n                \'bypassed_uls\', \'processed_uls\', \'capacity_uls\'}\n    missing = required.difference(df.columns)\n    if missing:\n        raise ValueError(f\'Screening columns missing: {sorted(missing)}\')\n    working = df.loc[df[\'Step\'] > 0].copy()\n    if len(working) != 365:\n        raise ValueError(f\'Expected 365 operating days, found {len(working)}\')\n    admitted = working[\'screened_uls\'] + working[\'screened_backlog_uls\']\n    if not (working[\'arrived_uls\'] == working[\'screened_uls\'] + working[\'bypassed_uls\']).all():\n        raise ValueError(\'Arrival accounting failed\')\n    if not (admitted <= working[\'capacity_uls\']).all():\n        raise ValueError(\'Screening capacity exceeded\')\n    if not (working[list(required - {\'Step\'})] >= 0).all().all():\n        raise ValueError(\'Negative screening count\')\n    arrivals = int(working.arrived_uls.sum())\n    capacity = int(working.capacity_uls.sum())\n    return {\n        \'screen_arrivals_uls\': arrivals,\n        \'screen_new_uls\': int(working.screened_uls.sum()),\n        \'screen_backlog_uls\': int(working.screened_backlog_uls.sum()),\n        \'screen_total_uls\': int(admitted.sum()),\n        \'screen_bypassed_uls\': int(working.bypassed_uls.sum()),\n        \'screen_completed_uls\': int(working.processed_uls.sum()),\n        \'screen_utilization_pct\': 100 * admitted.sum() / capacity if capacity else float(\'nan\'),\n        \'screen_bypass_pct\': 100 * working.bypassed_uls.sum() / arrivals if arrivals else float(\'nan\'),\n        \'screen_full_days\': int((admitted == working.capacity_uls).sum()),\n    }\n\n\ndef summarize(path: Path) -> dict:\n    if not path.is_file():\n        raise FileNotFoundError(path)\n    screening = pd.read_excel(path, sheet_name=\'Screening\')\n    fulfill = pd.read_excel(path, sheet_name=\'Fulfillment\')\n    detention = pd.read_excel(path, sheet_name=\'Detention\')\n    flows = pd.read_excel(path, sheet_name=\'Flows\')\n    stock = pd.read_excel(path, sheet_name=\'Stock\')\n    result = screening_summary(screening)\n    last = fulfill.loc[fulfill.Step.idxmax()]\n    for stream in (\'producer\', \'pooler\'):\n        keys = [\'created_rtis\', \'due_rtis\', \'on_time_rtis\', \'late_rtis\',\n                \'outstanding_due_rtis\', \'not_yet_due_rtis\', \'on_time_fill_rate_pct\']\n        for key in keys:\n            value = last[f\'{stream}_{key}\']\n            result[f\'{stream}_{key}\'] = float(value) if key.endswith(\'_pct\') else int(value)\n        if result[f\'{stream}_created_rtis\'] != sum(result[f\'{stream}_{x}\'] for x in\n              (\'on_time_rtis\',\'late_rtis\',\'outstanding_due_rtis\',\'not_yet_due_rtis\')):\n            raise ValueError(f\'{stream}: fulfillment mass balance mismatch\')\n\n    for node in (\'pool\',\'pro\',\'r_dc\',\'r_pos\'):\n        daily = detention.loc[detention.Step > 0]\n        d = float(daily[f\'{node}_total_days\'].sum())\n        n = int(daily[f\'{node}_departures\'].sum())\n        result[f\'detention_{node}_completed_mean_days\'] = d / n if n else float(\'nan\')\n        result[f\'detention_{node}_departures_rtis\'] = n\n\n    returned = int(flows.loc[(flows.Origin == \'RDC\') & (flows.Destination == \'POOL\'), \'Quantity\'].sum())\n    sent = int(flows.loc[(flows.Origin == \'POOL\') & flows.Destination.astype(str).str.startswith(\'PRO_\'), \'Quantity\'].sum())\n    result[\'flow_rdc_pool_rtis\'] = returned\n    result[\'flow_pool_pro_rtis\'] = sent\n    result[\'return_to_dispatch_pct\'] = (100*returned/sent if sent else float(\'nan\'))\n    stock_daily = stock.loc[stock.Step > 0].groupby([\'Step\',\'Warehouse\'])[\'Quantity\'].sum().unstack(fill_value=0)\n    for key in (\'POOL_WASHED\',\'POOL_UNWASHED\',\'POOL_BUFFER\'):\n        if key in stock_daily.columns:\n            result[f\'stock_{key.lower()}_average_rtis\'] = float(stock_daily[key].mean())\n            result[f\'stock_{key.lower()}_last_rtis\'] = int(stock_daily[key].iloc[-1])\n    return result\n\n\nUNITS = {\n    \'screen_arrivals_uls\':\'ULs\',\'screen_new_uls\':\'ULs\',\'screen_backlog_uls\':\'ULs\',\n    \'screen_total_uls\':\'ULs\',\'screen_bypassed_uls\':\'ULs\',\'screen_completed_uls\':\'ULs\',\n    \'screen_utilization_pct\':\'percentage points\',\'screen_bypass_pct\':\'percentage points\',\n    \'screen_full_days\':\'days\',\'return_to_dispatch_pct\':\'percentage points\',\n}\n\n\ndef unit_for(key):\n    if key in UNITS:\n        return UNITS[key]\n    if key.endswith(\'_rtis\'):\n        return \'RTIs\'\n    if key.endswith(\'_days\'):\n        return \'days\'\n    if key.endswith(\'_pct\'):\n        return \'percentage points\'\n    return \'count\'\n\n\ndef display(value, unit):\n    return f\'{value:,.2f}\' if unit in (\'percentage points\',\'days\') or isinstance(value,float) else f\'{value:,}\'\n\n\ndef main():\n    parser=argparse.ArgumentParser(description=__doc__)\n    parser.add_argument(\'baseline\', type=Path)\n    parser.add_argument(\'traceability\',type=Path)\n    parser.add_argument(\'--output-dir\',type=Path,default=Path(\'analysis/reports\'))\n    args=parser.parse_args()\n    baseline=summarize(args.baseline)\n    trace=summarize(args.traceability)\n    if set(baseline) != set(trace):\n        raise ValueError(\'Scenario metrics differ: verify consistent model versions\')\n    rows=[]\n    for key,b in baseline.items():\n        t=trace[key]; d=t-b\n        rows.append(dict(Metric=key, Unit=unit_for(key), Baseline=b, Traceability=t, Delta=d))\n    results=pd.DataFrame(rows)\n    args.output_dir.mkdir(parents=True,exist_ok=True)\n    csv_path=args.output_dir/\'task1_comparison.csv\'\n    report_path=args.output_dir/\'task1_comparison.md\'\n    results.to_csv(csv_path,index=False)\n    priority=[\'producer_on_time_fill_rate_pct\',\'pooler_on_time_fill_rate_pct\',\n              \'producer_outstanding_due_rtis\',\'pooler_outstanding_due_rtis\',\n              \'screen_arrivals_uls\',\'screen_total_uls\',\'screen_backlog_uls\',\n              \'screen_utilization_pct\',\'screen_bypass_pct\',\'screen_full_days\',\n              \'stock_pool_unwashed_average_rtis\',\'stock_pool_washed_average_rtis\',\n              \'flow_pool_pro_rtis\',\'flow_rdc_pool_rtis\',\n              \'detention_pool_completed_mean_days\',\'detention_pro_completed_mean_days\',\n              \'detention_r_dc_completed_mean_days\',\'detention_r_pos_completed_mean_days\']\n    lines=[\'# Team 7 — Task 1 baseline versus RFID (one seed)\', \'\',\n           f\'Baseline workbook: `{args.baseline}`\',\n           f\'Traceability workbook: `{args.traceability}`\',\'\',\n           \'This is a descriptive comparison, **not** a statistically supported improvement claim.\',\n           \'Same seed controls repeatability within each configuration, but policies may consume random draws differently.\',\n           \'Differences in delivery volumes can therefore reflect both policy and differing stochastic trajectories.\',\'\',\n           \'| KPI | Baseline | Traceability | Difference | Units |\',\n           \'|---|---:|---:|---:|---|\']\n    for key in priority:\n        if key not in baseline: continue\n        unit=unit_for(key)\n        lines.append(f\'| {key} | {display(baseline[key],unit)} | {display(trace[key],unit)} | {display(trace[key]-baseline[key],unit)} | {unit} |\')\n    lines+=[\'\', \'## Interpretation cautions\',\'\',\n            \'- Screening **operations** include both new arrivals and previously bypassed backlog ULs.\',\n            \'- Full capacity days must use new + backlog screening, not new arrivals only.\',\n            \'- Order fill rate is delivered-on-time RTIs / due RTIs (not the fraction of order lines fully satisfied).\',\n            \'- Average detention here covers **completed stays** only; unresolved stock is right-censored.\',\n            \'- Return-to-dispatch is an aggregate flow ratio, not a reuse probability.\',\n            \'- An RFID scenario cannot be called better solely because utilization is high; service and circularity must also be assessed.\',\n            \'\', \'## Decision gate\', \'\',\n            \'Do not merge a traceability policy solely based on passing unit tests. Verify that both full-year runs complete, all accounting checks pass, and the proposed rules have acceptable service-level consequences.\',\n            \'For Task 2, run multiple independent seeds and report uncertainty.\', \'\']\n    report_path.write_text(\'\\n\'.join(lines),encoding=\'utf-8\')\n    print(\'\\nCRITICAL TASK 1 METRICS — baseline vs traceability\')\n    for key in priority:\n        if key not in baseline:continue\n        unit=unit_for(key)\n        print(f\'{key:46} {display(baseline[key],unit):>14} -> {display(trace[key],unit):>14} (delta {display(trace[key]-baseline[key],unit)})\')\n    print(f\'\\nReports: {csv_path.resolve()}\\n         {report_path.resolve()}\')\n\n\nif __name__==\'__main__\':\n    main()\n'
append_new('analysis/compare_task1_scenarios.py', comparison_text)
test_text = '"""Regression tests for the screening accounting in the Task 1 comparison."""\nimport unittest\nimport pandas as pd\nfrom analysis.compare_task1_scenarios import screening_summary\n\n\nclass Task1ReportingTests(unittest.TestCase):\n    def test_backlog_counts_toward_full_screening_days(self):\n        rows = []\n        for day in range(366):\n            # One operational day at full capacity: 12 new + 8 backlog.\n            # Others have zero arrivals and zero operations.\n            rows.append(dict(Step=day, arrived_uls=12 if day==1 else 0,\n                             screened_uls=12 if day==1 else 0,\n                             screened_backlog_uls=8 if day==1 else 0,\n                             bypassed_uls=0, processed_uls=0, capacity_uls=20))\n        data = pd.DataFrame(rows)\n        summary = screening_summary(data)\n        self.assertEqual(summary[\'screen_full_days\'],1)\n        self.assertEqual(summary[\'screen_total_uls\'],20)\n        self.assertAlmostEqual(summary[\'screen_utilization_pct\'],100*20/(365*20))\n\n    def test_screening_rejects_more_than_capacity(self):\n        rows=[dict(Step=day, arrived_uls=12 if day==1 else 0,\n                   screened_uls=12 if day==1 else 0, screened_backlog_uls=9 if day==1 else 0,\n                   bypassed_uls=0, processed_uls=0, capacity_uls=20) for day in range(366)]\n        with self.assertRaises(ValueError):\n            screening_summary(pd.DataFrame(rows))\n\n\nif __name__==\'__main__\':\n    unittest.main()\n'
append_new('tests/test_task1_comparison.py', test_text)

for path, content in changes.items():
    (ROOT / path).write_text(content, encoding='utf-8')
for path, content in new_files.items():
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
print('Task 1 v2 repair applied. Run tests and compare corrected scenarios before committing.')
