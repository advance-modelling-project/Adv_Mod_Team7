"""Apply measured, shortage-aware RFID screening to Team 7's Task 1 v2 branch.

Run from the ROOT of the original Adv_Mod_Team7 checkout, AFTER v2:
    python tools/apply_task1_v3.py

All anchors are checked before writing any file. Baseline decision logic stays unchanged.
"""
from pathlib import Path

ROOT = Path.cwd()
PATCHED = {}

def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    s = PATCHED.get(path, p.read_text(encoding="utf-8"))
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one anchor; found {count}. NO FILES WRITTEN.")
    PATCHED[path] = s.replace(old, new, 1)
    print("Validated", path)

# A pure helper, so selection logic is independently testable without running Mesa.
HELPER = '''def select_shortage_aware_uls(candidates, washed_deficits, capacity):
    """Select <= capacity whole ULs, using due washed-only deficits first.

    washed_deficits maps CrateType to outstanding UL demand after subtracting
    already washed/in-process supply. Prefer a mix of types when several are
    short. Within a type, RFID product history and detention break ties.
    No inventory list is mutated here; screen_uls removes selected ULs later.
    """
    from collections import defaultdict
    by_type = defaultdict(list)
    for ul in candidates:
        by_type[ul.crate_type].append(ul)
    for ul_list in by_type.values():
        ul_list.sort(key=lambda ul: (_ul_dirty_history_count(ul),
                                    _ul_average_detention(ul)), reverse=True)

    selected = []
    selected_by_type = defaultdict(int)
    left = {ct: max(0, int(n)) for ct, n in washed_deficits.items()}
    while len(selected) < capacity and any(by_type.values()):
        needy = [ct for ct, items in by_type.items()
                 if items and left.get(ct, 0) > 0]
        if needy:
            # Diminishing priority shares scarce capacity among short types;
            # this prevents blindly taking the first 20 loads of one type.
            ct = max(needy, key=lambda c: (left[c] / (1 + selected_by_type[c]),
                                           left[c], c.name))
            left[ct] -= 1
        else:
            ct = max((ct for ct, items in by_type.items() if items),
                     key=lambda c: (_ul_dirty_history_count(by_type[c][0]),
                                    _ul_average_detention(by_type[c][0]), c.name))
        selected.append(by_type[ct].pop(0))
        selected_by_type[ct] += 1
    return selected


'''

replace_once('agents.py',
    'class Pooler_Agent(mesa.Agent):\n',
    HELPER + 'class Pooler_Agent(mesa.Agent):\n')

OLD = '''            new_ids = {ul.id for ul in uls}
            dirty_candidates = [
                ul for stock in self.unwashed_stock_pool.values() for ul in stock
                if _ul_dirty_history_count(ul) > 0
            ]
            dirty_candidates.sort(
                key=lambda ul: (_ul_dirty_history_count(ul), _ul_average_detention(ul)),
                reverse=True,
            )
            uls_to_screen = dirty_candidates[:remaining_capacity]
            remaining_capacity -= len(uls_to_screen)

            # Use any remaining capacity to inspect clean ULs from today's arrivals;
            # this retains a chance to detect the modelled 5% breakage during recovery.
            clean_new = [ul for ul in uls if ul not in uls_to_screen and _ul_dirty_history_count(ul) == 0]
            if remaining_capacity > 0 and clean_new:
                uls_to_screen.extend(random.sample(clean_new, min(remaining_capacity, len(clean_new))))
'''
NEW = '''            new_ids = {ul.id for ul in uls}
            lookahead = current_step + self.processing_lead_time
            washed_deficits = {}
            for ct in CrateType:
                # Only washed-only orders due by the next recovery completion
                # require preferential recovery; flexible orders do not.
                washed_due_uls = sum(
                    order.quantity for order in self.order_book
                    if order.crate_type == ct and order.needs_washed is True
                    and order.creation_step + order.lead_time <= lookahead
                )
                already_ready = len(self.washed_stock_pool[ct])
                processing = sum(1 for ul in self.processing_buffer if ul.crate_type == ct)
                washed_deficits[ct] = max(0, washed_due_uls - already_ready - processing)

            recovery_candidates = [
                ul for stock in self.unwashed_stock_pool.values() for ul in stock
            ]
            # RFID policy v3: washed-order shortages decide crate-type priority;
            # previous product and detention determine which UL within that type.
            # This does not change the 20-UL/day screening limit.
            uls_to_screen = select_shortage_aware_uls(
                recovery_candidates, washed_deficits, remaining_capacity
            )
'''
replace_once('agents.py', OLD, NEW)

replace_once('agents.py',
'''        for ul in uls_to_screen:
            self.processing_buffer.append(ul)
            self.processing_times[ul.id] = current_step
            for rti in ul.rtis:
                rti.under_processing = True
''',
'''        # Monitoring only; report screened/bypassed ULs separately per crate type.
        type_log = self.model.daily_log.get('screening_types')
        if type_log is not None:
            new_ul_ids = {ul.id for ul in uls}
            screened_ids = {ul.id for ul in uls_to_screen}
            for ul in uls:
                type_log[ul.crate_type]['arrived_uls'] += 1
                if ul.id not in screened_ids:
                    type_log[ul.crate_type]['bypassed_uls'] += 1
            for ul in uls_to_screen:
                metric = 'screened_new_uls' if ul.id in new_ul_ids else 'screened_backlog_uls'
                type_log[ul.crate_type][metric] += 1

        for ul in uls_to_screen:
            self.processing_buffer.append(ul)
            self.processing_times[ul.id] = current_step
            for rti in ul.rtis:
                rti.under_processing = True
''')

replace_once('agents.py',
'''        # ULs finishing recovery today (may differ from ULs screened today).
        self.model.daily_log['screening']['processed_uls'] += len(ready_uls)
''',
'''        # ULs finishing recovery today (may differ from ULs screened today).
        self.model.daily_log['screening']['processed_uls'] += len(ready_uls)
        if 'screening_types' in self.model.daily_log:
            for ul in ready_uls:
                self.model.daily_log['screening_types'][ul.crate_type]['processed_uls'] += 1
''')

replace_once('model.py',
'''        # Measurement-only order metrics (all quantities in RTIs).
''',
'''        # Screening operations by crate type, to verify allocation and starvation.
        for ct in CrateType:
            for metric in ('arrived_uls', 'screened_new_uls', 'screened_backlog_uls',
                           'bypassed_uls', 'processed_uls'):
                reporters[f'ScreeningByType|{ct.name}|{metric}'] = (
                    lambda m, c=ct, k=metric: m.daily_log['screening_types'][c][k]
                )

        # Measurement-only order metrics (all quantities in RTIs).
''')

replace_once('model.py',
'''        self.daily_log = {
            'screening': {
''',
'''        self.daily_log = {
            'screening_types': {
                ct: {key: 0 for key in ('arrived_uls', 'screened_new_uls',
                                       'screened_backlog_uls', 'bypassed_uls',
                                       'processed_uls')} for ct in CrateType
            },
            'screening': {
''')

replace_once('model.py',
'''            fulfillment_cols = [c for c in df_wide.columns if c.startswith('Fulfillment|')]
''',
'''            # One row per simulation day, crate type and screening operation.
            by_type_cols = [c for c in df_wide.columns if c.startswith('ScreeningByType|')]
            if by_type_cols:
                by_type_df = df_wide[['Step', *by_type_cols]].melt(
                    id_vars=['Step'], var_name='Key', value_name='ULs'
                )
                by_type_df[['Category', 'Crate Type', 'Metric']] = (
                    by_type_df['Key'].str.split('|', expand=True)
                )
                by_type_df[['Step', 'Crate Type', 'Metric', 'ULs']].to_excel(
                    writer, sheet_name='ScreeningByType', index=False
                )

            fulfillment_cols = [c for c in df_wide.columns if c.startswith('Fulfillment|')]
''')

# Keep the existing lightweight traceability test harness representative of the
# complete Pooler state required by the new policy.
replace_once('tests/test_traceability_policy.py',
"""        pool = SimpleNamespace(
            model=model, processing_buffer=[], processing_times={}, processing_lead_time=1,
            unwashed_stock_pool={ct: [] for ct in CrateType},
        )
""",
"""        pool = SimpleNamespace(
            model=model, processing_buffer=[], processing_times={}, processing_lead_time=1,
            order_book=[],
            washed_stock_pool={ct: [] for ct in CrateType},
            unwashed_stock_pool={ct: [] for ct in CrateType},
        )
""")

# Do not write anything until every anchor passed and Python syntax is verified.
for path, content in PATCHED.items():
    compile(content, path, 'exec')
for path, content in PATCHED.items():
    (ROOT / path).write_text(content, encoding='utf-8', newline='\n')
print('Applied v3 shortage-aware screening and per-type logging. Run unit tests first.')
