"""Apply Team 7 Task 1 RFID traceability scenario to the repository.

Run from repository root:
    python tools/apply_traceability_scenario.py

The script fails safely if the expected main-branch source blocks are not found.
"""
from pathlib import Path

ROOT = Path.cwd()
PATCHED_FILES = {}
NEW_FILES = {}


def replace_once(path: str, old: str, new: str) -> None:
    file_path = ROOT / path
    text = PATCHED_FILES.get(path, file_path.read_text(encoding="utf-8"))
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}. No files have been written.")
    PATCHED_FILES[path] = text.replace(old, new, 1)
    print(f"Validated patch block in {path}")


def append_new(path: str, content: str) -> None:
    file_path = ROOT / path
    if file_path.exists() or path in NEW_FILES:
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")
    NEW_FILES[path] = content
    print(f"Prepared new file {path}")


def main() -> None:
    # 1) Scenario switch.
    replace_once(
        "config.py",
        "    POOL_PROCESSING_TIME: int = 1\n",
        "    POOL_PROCESSING_TIME: int = 1\n    # False reproduces the assignment's random baseline policies; True enables RFID rules.\n    TRACEABILITY_ENABLED: bool = False\n",
    )

    # 2) RTI-level RFID detention-time state and common selection helpers.
    replace_once(
        "agents.py",
        "        self.broken = False\n        self.dirty = False\n\n\nclass Pooler_Agent(mesa.Agent):\n",
        """        self.broken = False
        self.dirty = False

    @property
    def detention_time(self) -> int:
        \"\"\"Current days spent at the RTI's current node (RFID tag field).\"\"\"
        return max(0, self.model.steps - self.arrival_step)

    def move_to_transport(self):
        \"\"\"Record node dwell time and reset the tag timer on departure.\"\"\"
        detention_log = self.model.daily_log.get('detention', {})
        node = self.location.value
        if node in detention_log:
            detention_log[node]['total_days'] += self.detention_time
            detention_log[node]['departures'] += 1
        self.arrival_step = self.model.steps
        self.location = LocationType.TRANSPORT


def _ul_dirty_history_count(ul: UnitLoad) -> int:
    \"\"\"Count RTIs whose RFID product history indicates a dirty-making product.\"\"\"
    return sum(1 for rti in ul.rtis if rti.product is not None and rti.product.makes_dirty)


def _ul_average_detention(ul: UnitLoad) -> float:
    \"\"\"Average current node detention time of the RTIs in a unit load.\"\"\"
    return (sum(rti.detention_time for rti in ul.rtis) / len(ul.rtis)) if ul.rtis else 0.0


class Pooler_Agent(mesa.Agent):
""",
    )

    # 3) Pooler retrieval: baseline random; traceability oldest-first and no dirty-unwashed dispatch.
    replace_once(
        "agents.py",
        """    def extract_uls(self, crate_type: CrateType, needs_washed: Optional[bool], quantity_uls: int) -> List[UnitLoad]:
        primary_stock = self.washed_stock_pool[crate_type] if needs_washed else self.unwashed_stock_pool[crate_type]
        secondary_stock = [] if needs_washed else self.washed_stock_pool[crate_type]

        primary_available = len(primary_stock)
        selected_uls = []

        # IMPROVEMENT: Removed 2 occurrences of random.sample() from the baseline code.
        # Since UnitLoads of the same crate type and wash status are identical (fungible),
        # random extraction is unnecessary. Replaced with O(1) list slicing for a massive speed boost.
        if primary_available >= quantity_uls:
            selected_uls = primary_stock[:quantity_uls]
            del primary_stock[:quantity_uls]
        else:
            selected_uls.extend(primary_stock)
            primary_stock.clear()
            needed = quantity_uls - primary_available
            if len(secondary_stock) >= needed:
                selected_uls.extend(secondary_stock[:needed])
                del secondary_stock[:needed]
            else:
                selected_uls.extend(secondary_stock)
                secondary_stock.clear()
        return selected_uls
""",
        """    def _take_uls(self, stock: List[UnitLoad], quantity_uls: int, candidates=None) -> List[UnitLoad]:
        candidates = stock if candidates is None else candidates
        quantity = min(quantity_uls, len(candidates))
        if quantity <= 0:
            return []
        if self.model.config.TRACEABILITY_ENABLED:
            selected = sorted(candidates, key=_ul_average_detention, reverse=True)[:quantity]
        else:
            # The assignment baseline specifies random stock retrieval.
            selected = random.sample(candidates, quantity)
        for ul in selected:
            stock.remove(ul)
        return selected

    def extract_uls(self, crate_type: CrateType, needs_washed: Optional[bool], quantity_uls: int) -> List[UnitLoad]:
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
""",
    )

    # 4) Pooler outbound movement uses the common RFID departure update.
    replace_once(
        "agents.py",
        """                for ul in extracted_uls:
                    for rti in ul.rtis:
                        rti.location = LocationType.TRANSPORT

                target_pro = self.model.producers_by_id[order.issuer]
""",
        """                for ul in extracted_uls:
                    for rti in ul.rtis:
                        rti.move_to_transport()

                target_pro = self.model.producers_by_id[order.issuer]
""",
    )

    # 5) Pooler screening: baseline random inbound selection; RFID dirty-first plus backlog recovery.
    replace_once(
        "agents.py",
        """    def screen_uls(self, uls: List[UnitLoad], current_step: int):
        num_uls_to_screen = min(len(uls), self.model.config.POOL_SCREENING_CAPACITY)

        # IMPROVEMENT: Removed 1 occurrence of random.sample() from the baseline code.
        # Bypassed vs screened unit loads don't need randomized selection because
        # they are freshly arrived and homogenous. Used list slicing instead for speed.
        uls_to_screen = uls[:num_uls_to_screen] if num_uls_to_screen > 0 else []
        uls_to_bypass = uls[num_uls_to_screen:]

        # Measurement only: do not change how loads are selected.
        screen_log = self.model.daily_log['screening']
        screen_log['arrived_uls'] += len(uls)
        screen_log['screened_uls'] += len(uls_to_screen)
        screen_log['bypassed_uls'] += len(uls_to_bypass)

        for ul in uls_to_screen:
            self.processing_buffer.append(ul)
            self.processing_times[ul.id] = current_step
            for rti in ul.rtis:
                rti.under_processing = True

        for ul in uls_to_bypass:
            self.unwashed_stock_pool[ul.crate_type].append(ul)
""",
        """    def screen_uls(self, uls: List[UnitLoad], current_step: int):
        screen_log = self.model.daily_log['screening']
        screen_log.setdefault('screened_backlog_uls', 0)
        screen_log['arrived_uls'] += len(uls)
        capacity = self.model.config.POOL_SCREENING_CAPACITY
        used_today = screen_log['screened_uls'] + screen_log['screened_backlog_uls']
        remaining_capacity = max(0, capacity - used_today)

        if not self.model.config.TRACEABILITY_ENABLED:
            # Faithful baseline: randomly select only today's inbound ULs.
            count = min(len(uls), remaining_capacity)
            uls_to_screen = random.sample(uls, count) if count > 0 else []
            uls_to_bypass = [ul for ul in uls if ul not in uls_to_screen]
            screen_log['screened_uls'] += len(uls_to_screen)
            screen_log['bypassed_uls'] += len(uls_to_bypass)
            for ul in uls_to_bypass:
                self.unwashed_stock_pool[ul.crate_type].append(ul)
        else:
            # All new returns first enter the unwashed stock. The RFID history is
            # then used to prioritize dirty backlog and today's dirty arrivals.
            for ul in uls:
                if ul not in self.unwashed_stock_pool[ul.crate_type]:
                    self.unwashed_stock_pool[ul.crate_type].append(ul)

            new_ids = {ul.id for ul in uls}
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

            screened_new = sum(1 for ul in uls_to_screen if ul.id in new_ids)
            screened_backlog = len(uls_to_screen) - screened_new
            screen_log['screened_uls'] += screened_new
            screen_log['screened_backlog_uls'] += screened_backlog
            # Bypass is defined for today's arrivals only; backlog screening is reported separately.
            screen_log['bypassed_uls'] = screen_log['arrived_uls'] - screen_log['screened_uls']

            for ul in uls_to_screen:
                self.unwashed_stock_pool[ul.crate_type].remove(ul)

        for ul in uls_to_screen:
            self.processing_buffer.append(ul)
            self.processing_times[ul.id] = current_step
            for rti in ul.rtis:
                rti.under_processing = True
""",
    )

    # 6) Preserve product history until recovery is completed, as in the assignment RFID sequence.
    replace_once(
        "agents.py",
        """        rti.dirty = False
        rti.washed = True
        return rti

    def evaluate_rti_condition(self, rti: RTI_Agent):
        if random.random() < self.model.config.RTI_BREAKAGE_RATE:
            rti.broken = True
        if not rti.dirty and rti.product is not None and rti.product.makes_dirty:
            rti.dirty = True
        rti.product = None
""",
        """        rti.dirty = False
        rti.washed = True
        # The tag's previous-product field is cleared only after recovery is complete.
        rti.product = None
        return rti

    def evaluate_rti_condition(self, rti: RTI_Agent):
        if random.random() < self.model.config.RTI_BREAKAGE_RATE:
            rti.broken = True
        if not rti.dirty and rti.product is not None and rti.product.makes_dirty:
            rti.dirty = True
""",
    )

    # 7) Re-screen dirty unwashed backlog on days with spare screening capacity.
    replace_once(
        "agents.py",
        """    def step(self):
        self.process_uls()
        self.fulfill_orders()


class Producer_Agent(mesa.Agent):
""",
        """    def step(self):
        self.process_uls()
        if self.model.config.TRACEABILITY_ENABLED:
            # Continue recovering previously bypassed dirty ULs when capacity is available.
            self.screen_uls([], self.model.steps)
        self.fulfill_orders()


class Producer_Agent(mesa.Agent):
""",
    )

    # Match the assignment RFID example: the previous-product field is cleared when an RTI is received into producer stock.
    replace_once(
        "agents.py",
        """                rti.location = LocationType.PRO
                rti.washed = False
                rti.arrival_step = current_step
""",
        """                rti.location = LocationType.PRO
                rti.washed = False
                rti.product = None
                rti.arrival_step = current_step
""",
    )

    # 8) Producer retrieval: random in baseline, oldest-first with RFID in traceability.
    replace_once(
        "agents.py",
        """    def extract_rtis(self, quantity: int, crate_type: CrateType) -> List[RTI_Agent]:
        available = self.forward_stock_pro[crate_type]
        qty_to_sample = min(quantity, len(available))
        if qty_to_sample == 0: return []

        # IMPROVEMENT: Removed 1 occurrence of random.sample() from the baseline code.
        # Empty RTIs are identical, so picking randomly adds linear overhead O(N) for no reason.
        # Replaced with O(1) list slicing.
        rtis_to_send = available[:qty_to_sample]
        del available[:qty_to_sample]
        return rtis_to_send
""",
        """    def extract_rtis(self, quantity: int, crate_type: CrateType) -> List[RTI_Agent]:
        available = self.forward_stock_pro[crate_type]
        qty_to_select = min(quantity, len(available))
        if qty_to_select == 0:
            return []
        if self.model.config.TRACEABILITY_ENABLED:
            rtis_to_send = sorted(available, key=lambda rti: rti.detention_time, reverse=True)[:qty_to_select]
        else:
            # The assignment baseline specifies random stock retrieval.
            rtis_to_send = random.sample(available, qty_to_select)
        for rti in rtis_to_send:
            available.remove(rti)
        return rtis_to_send
""",
    )

    replace_once(
        "agents.py",
        """                for rti in extracted_rtis:
                    rti.is_filled = True
                    rti.product = order.product
                    rti.location = LocationType.TRANSPORT
""",
        """                for rti in extracted_rtis:
                    rti.is_filled = True
                    rti.product = order.product
                    rti.move_to_transport()
""",
    )

    # 9) RDC dispatch and return-truck retrieval.
    replace_once(
        "agents.py",
        """        allocation = self.allocate_rtis(rtis)
        for rpos, rti_list in allocation.items():
            for rti in rti_list:
                rti.location = LocationType.TRANSPORT
            rpos.receive_rtis(rti_list)
""",
        """        allocation = self.allocate_rtis(rtis)
        for rpos, rti_list in allocation.items():
            for rti in rti_list:
                rti.move_to_transport()
            rpos.receive_rtis(rti_list)
""",
    )

    replace_once(
        "agents.py",
        """        # FIX: Restored random.shuffle before slicing to prevent biased extraction (e.g., always taking TYPE_1 first).
        # Ensures uniform return flows for different crate types back to the pooler.
        random.shuffle(all_available_uls)
        uls_to_ship = all_available_uls[:num_trucks * self.model.config.TRUCK_CAPACITY]
""",
        """        if self.model.config.TRACEABILITY_ENABLED:
            # Prioritize the ULs with the longest RFID detention time at the RDC.
            all_available_uls.sort(key=_ul_average_detention, reverse=True)
        else:
            # Preserve the assignment baseline's random stock retrieval.
            random.shuffle(all_available_uls)
        uls_to_ship = all_available_uls[:num_trucks * self.model.config.TRUCK_CAPACITY]
""",
    )

    replace_once(
        "agents.py",
        """            for rti in ul.rtis:
                rti.location = LocationType.TRANSPORT
            self.model.daily_log['movements']['rdc_to_pool'][ul.crate_type] += len(ul.rtis)
""",
        """            for rti in ul.rtis:
                rti.move_to_transport()
            self.model.daily_log['movements']['rdc_to_pool'][ul.crate_type] += len(ul.rtis)
""",
    )

    # 10) RPOS return-UL formation: random in baseline, oldest-first with RFID in traceability.
    replace_once(
        "agents.py",
        """            # FIX: Restored random.shuffle to maintain realistic detention time variations.
            random.shuffle(available_rtis)

            num_full_uls = len(available_rtis) // cfg.UL_SIZE
""",
        """            if self.model.config.TRACEABILITY_ENABLED:
                available_rtis.sort(key=lambda rti: rti.detention_time, reverse=True)
            else:
                random.shuffle(available_rtis)

            num_full_uls = len(available_rtis) // cfg.UL_SIZE
""",
    )

    replace_once(
        "agents.py",
        """                for rti in rtis_for_ul: rti.location = LocationType.TRANSPORT
                uls_to_dispatch.append(UnitLoad(crate_type=ct, rtis=rtis_for_ul))
""",
        """                for rti in rtis_for_ul:
                    rti.move_to_transport()
                uls_to_dispatch.append(UnitLoad(crate_type=ct, rtis=rtis_for_ul))
""",
    )

    # 11) Detention and screening metrics in the model output.
    replace_once(
        "model.py",
        """            'Screening|processed_uls': lambda m: m.daily_log['screening']['processed_uls'],
            'Screening|capacity_uls': lambda m: m.config.POOL_SCREENING_CAPACITY,
            'Screening|utilization_pct': lambda m: (
                100.0 * m.daily_log['screening']['screened_uls'] / m.config.POOL_SCREENING_CAPACITY
                if m.config.POOL_SCREENING_CAPACITY > 0 else None
            ),
""",
        """            'Screening|processed_uls': lambda m: m.daily_log['screening']['processed_uls'],
            'Screening|screened_backlog_uls': lambda m: m.daily_log['screening']['screened_backlog_uls'],
            'Screening|capacity_uls': lambda m: m.config.POOL_SCREENING_CAPACITY,
            'Screening|utilization_pct': lambda m: (
                100.0 * (m.daily_log['screening']['screened_uls'] + m.daily_log['screening']['screened_backlog_uls']) / m.config.POOL_SCREENING_CAPACITY
                if m.config.POOL_SCREENING_CAPACITY > 0 else None
            ),
""",
    )

    replace_once(
        "model.py",
        """        # Measurement-only order metrics (all quantities in RTIs).
        for field in self.fulfillment_snapshot:
""",
        """        # RFID detention-time metrics: total node-days and RTIs departing each node.
        for node in ('pool', 'pro', 'r_dc', 'r_pos'):
            reporters[f'Detention|{node}|total_days'] = lambda m, n=node: m.daily_log['detention'][n]['total_days']
            reporters[f'Detention|{node}|departures'] = lambda m, n=node: m.daily_log['detention'][n]['departures']
            reporters[f'Detention|{node}|average_days'] = lambda m, n=node: (
                m.daily_log['detention'][n]['total_days'] / m.daily_log['detention'][n]['departures']
                if m.daily_log['detention'][n]['departures'] else None
            )

        # Measurement-only order metrics (all quantities in RTIs).
        for field in self.fulfillment_snapshot:
""",
    )

    replace_once(
        "model.py",
        """                'bypassed_uls': 0,
                'processed_uls': 0,
            },
            'movements': {
""",
        """                'bypassed_uls': 0,
                'processed_uls': 0,
                'screened_backlog_uls': 0,
            },
            'detention': {
                'pool': {'total_days': 0, 'departures': 0},
                'pro': {'total_days': 0, 'departures': 0},
                'r_dc': {'total_days': 0, 'departures': 0},
                'r_pos': {'total_days': 0, 'departures': 0},
            },
            'movements': {
""",
    )

    replace_once(
        "model.py",
        """            fulfillment_cols = [c for c in df_wide.columns if c.startswith('Fulfillment|')]
            if fulfillment_cols:
                fulfillment_df = df_wide[['Step', *fulfillment_cols]].copy()
                fulfillment_df.columns = ['Step'] + [c.split('|', 1)[1] for c in fulfillment_cols]
                fulfillment_df.to_excel(writer, sheet_name='Fulfillment', index=False)
            tracker = getattr(self, 'order_tracker', None)
""",
        """            fulfillment_cols = [c for c in df_wide.columns if c.startswith('Fulfillment|')]
            if fulfillment_cols:
                fulfillment_df = df_wide[['Step', *fulfillment_cols]].copy()
                fulfillment_df.columns = ['Step'] + [c.split('|', 1)[1] for c in fulfillment_cols]
                fulfillment_df.to_excel(writer, sheet_name='Fulfillment', index=False)

            detention_cols = [c for c in df_wide.columns if c.startswith('Detention|')]
            if detention_cols:
                detention_df = df_wide[['Step', *detention_cols]].copy()
                detention_df.columns = ['Step'] + [c.split('|', 1)[1].replace('|', '_') for c in detention_cols]
                detention_df.to_excel(writer, sheet_name='Detention', index=False)

            tracker = getattr(self, 'order_tracker', None)
""",
    )

    # 12) Scenario and seed command-line options.
    PATCHED_FILES["main.py"] = """import argparse
import os
import random
from datetime import datetime
from config import SimulationConfig
from model import CLSC_Model


if __name__ == \"__main__\":
    parser = argparse.ArgumentParser(description=\"Run the Team 7 closed-loop supply-chain simulation.\")
    parser.add_argument(\"--scenario\", choices=(\"baseline\", \"traceability\"), default=\"baseline\")
    parser.add_argument(\"--seed\", type=int, default=None, help=\"Optional Python random seed for reproducibility.\")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    config = SimulationConfig(TRACEABILITY_ENABLED=(args.scenario == \"traceability\"))
    current_timestamp = datetime.now().strftime(\"%Y.%m.%d_%H.%M\")
    run_folder = f\"run_{args.scenario}_{current_timestamp}\"
    os.makedirs(run_folder, exist_ok=True)

    print(f\"\\nSimulation starting — scenario: {args.scenario}; seed: {args.seed}\\n\")
    model = CLSC_Model(config=config, results_dir=run_folder, run_timestamp=current_timestamp)

    for i in range(config.SIMULATION_STEPS):
        model.step()
        progress_pct = ((i + 1) / config.SIMULATION_STEPS) * 100
        filled = int(70 * (i + 1) / config.SIMULATION_STEPS)
        print(f\"\\r[{'█' * filled}{'░' * (70 - filled)}] {progress_pct:.1f}% | Step (Day) {i + 1:3d}/{config.SIMULATION_STEPS}\", end=\"\", flush=True)

    print(\"\\n\\nSimulation completed.\")
    model.export_to_excel()
"""
    print("Prepared main.py")

    # 13) Keep the screening validator consistent with the added backlog KPI.
    replace_once(
        "analysis/summarize_screening.py",
        """    expected = {'Step', 'arrived_uls', 'screened_uls', 'bypassed_uls',
                'processed_uls', 'capacity_uls', 'utilization_pct', 'bypass_rate_pct'}
""",
        """    expected = {'Step', 'arrived_uls', 'screened_uls', 'screened_backlog_uls', 'bypassed_uls',
                'processed_uls', 'capacity_uls', 'utilization_pct', 'bypass_rate_pct'}
""",
    )
    replace_once(
        "analysis/summarize_screening.py",
        """        'screened <= daily capacity': bool((df.screened_uls <= df.capacity_uls).all()),
""",
        """        'screened <= daily capacity': bool(((df.screened_uls + df.screened_backlog_uls) <= df.capacity_uls).all()),
""",
    )
    replace_once(
        "analysis/summarize_screening.py",
        """    screened = int(df.screened_uls.sum())
    bypassed = int(df.bypassed_uls.sum())
""",
        """    screened_new = int(df.screened_uls.sum())
    screened_backlog = int(df.screened_backlog_uls.sum())
    screened = screened_new + screened_backlog
    bypassed = int(df.bypassed_uls.sum())
""",
    )
    replace_once(
        "analysis/summarize_screening.py",
        """    print(f'Admitted to screening: {screened:,} ULs')
    print(f'Bypassed screening: {bypassed:,} ULs')
""",
        """    print(f'New arrivals screened: {screened_new:,} ULs')
    print(f'Previously bypassed dirty ULs re-screened: {screened_backlog:,} ULs')
    print(f'Total screening operations: {screened:,} ULs')
    print(f'Bypassed on arrival: {bypassed:,} ULs')
""",
    )

    # 14) Extend the existing screening unit tests' mock log and workbook fixture.
    replace_once(
        "tests/test_screening_kpis.py",
        """    return dict(arrived_uls=0, screened_uls=0, bypassed_uls=0, processed_uls=0)
""",
        """    return dict(arrived_uls=0, screened_uls=0, screened_backlog_uls=0, bypassed_uls=0, processed_uls=0)
""",
    )
    replace_once(
        "tests/test_screening_kpis.py",
        """            'Screening|screened_uls': [0, 2],
            'Screening|bypassed_uls': [0, 3],
""",
        """            'Screening|screened_uls': [0, 2],
            'Screening|screened_backlog_uls': [0, 0],
            'Screening|bypassed_uls': [0, 3],
""",
    )

    # 15) Add policy tests and a run-summary script.
    append_new("tests/test_traceability_policy.py", TESTS)
    append_new("analysis/summarize_traceability.py", SUMMARY)
    append_new("README_TRACEABILITY.md", README)

    # Commit all validated edits only after every expected source block has matched.
    for path, content in PATCHED_FILES.items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for path, content in NEW_FILES.items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print("\nTraceability scenario patch applied. Run the test suite before running either scenario.")


TESTS = r'''"""Tests for the RFID traceability decision rules."""
import unittest
from types import SimpleNamespace

from agents import Pooler_Agent, Producer_Agent, RTI_Agent, _ul_dirty_history_count
from config import CrateType, LocationType, SimulationConfig, UnitLoad


def rti(age=0, dirty_product=False):
    product = SimpleNamespace(makes_dirty=True) if dirty_product else None
    return SimpleNamespace(
        detention_time=age, product=product, under_processing=False,
        location=LocationType.PRO, arrival_step=0,
    )


def ul(age=0, dirty_product=False):
    return UnitLoad(CrateType.TYPE_1, [rti(age, dirty_product)])


class TraceabilityPolicyTests(unittest.TestCase):
    def test_dirty_history_uses_product_tag_not_hidden_dirty_flag(self):
        clean = ul(dirty_product=False)
        dirty = ul(dirty_product=True)
        self.assertEqual(_ul_dirty_history_count(clean), 0)
        self.assertEqual(_ul_dirty_history_count(dirty), 1)

    def test_traceability_pooler_uses_oldest_clean_unwashed_first(self):
        old_clean, new_clean, dirty = ul(9), ul(2), ul(7, True)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        class PoolerHarness:
            _take_uls = Pooler_Agent._take_uls

        pool = PoolerHarness()
        pool.model = model
        pool.washed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool = {ct: [] for ct in CrateType}
        pool.unwashed_stock_pool[CrateType.TYPE_1] = [new_clean, dirty, old_clean]
        selected = Pooler_Agent.extract_uls(pool, CrateType.TYPE_1, False, 1)
        self.assertEqual(selected, [old_clean])
        self.assertIn(dirty, pool.unwashed_stock_pool[CrateType.TYPE_1])

    def test_traceability_screening_prioritizes_dirty_backlog(self):
        old_dirty = ul(8, True)
        new_clean = ul(0, False)
        model = SimpleNamespace(
            config=SimulationConfig(TRACEABILITY_ENABLED=True, POOL_SCREENING_CAPACITY=1),
            daily_log={'screening': {
                'arrived_uls': 0, 'screened_uls': 0, 'screened_backlog_uls': 0,
                'bypassed_uls': 0, 'processed_uls': 0,
            }},
            steps=10,
        )
        pool = SimpleNamespace(
            model=model, processing_buffer=[], processing_times={}, processing_lead_time=1,
            unwashed_stock_pool={ct: [] for ct in CrateType},
        )
        pool.unwashed_stock_pool[CrateType.TYPE_1].append(old_dirty)
        Pooler_Agent.screen_uls(pool, [new_clean], 10)
        log = model.daily_log['screening']
        self.assertIn(old_dirty, pool.processing_buffer)
        self.assertIn(new_clean, pool.unwashed_stock_pool[CrateType.TYPE_1])
        self.assertEqual(log['screened_backlog_uls'], 1)
        self.assertEqual(log['screened_uls'], 0)
        self.assertEqual(log['bypassed_uls'], 1)

    def test_producer_oldest_first(self):
        old, new = rti(7), rti(1)
        model = SimpleNamespace(config=SimulationConfig(TRACEABILITY_ENABLED=True))
        producer = SimpleNamespace(model=model, forward_stock_pro={CrateType.TYPE_1: [new, old]})
        selected = Producer_Agent.extract_rtis(producer, 1, CrateType.TYPE_1)
        self.assertEqual(selected, [old])

    def test_departure_records_node_detention_and_resets_timer(self):
        fake = SimpleNamespace(
            model=SimpleNamespace(
                steps=12,
                daily_log={'detention': {'pro': {'total_days': 0, 'departures': 0}}},
            ),
            location=LocationType.PRO,
            arrival_step=5,
            detention_time=7,
        )
        RTI_Agent.move_to_transport(fake)
        self.assertEqual(fake.model.daily_log['detention']['pro']['total_days'], 7)
        self.assertEqual(fake.model.daily_log['detention']['pro']['departures'], 1)
        self.assertEqual(fake.arrival_step, 12)
        self.assertEqual(fake.location, LocationType.TRANSPORT)


if __name__ == '__main__':
    unittest.main()
'''

SUMMARY = r'''"""Summarize RFID traceability KPIs from a simulation workbook.

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
'''

README = r'''# Team 7 — Task 1 RFID Traceability Scenario

## What this patch implements

The assignment manual defines Task 1 as designing and implementing a Traceability Scenario using RTI-level RFID information. This patch adds a scenario switch while retaining the baseline as a separate mode.

### Baseline mode

- Random stock retrieval at POOL, PRO, RDC and RPOS, consistent with the assignment description.
- Random selection of inbound ULs for the Pooler's daily screening capacity.
- No RFID-based prioritization.

### Traceability mode

1. **Oldest-first retrieval:** RTIs/ULs with the longest current-node detention time are selected first at POOL, PRO, RDC and RPOS.
2. **Dirty-history screening priority:** at POOL, ULs containing RTIs whose RFID product history identifies a dirty-making product are prioritized for screening. Previously bypassed dirty ULs can be screened on later days when capacity is available.
3. **Safe unwashed allocation:** orders that do not require washed crates use clean unwashed ULs first; dirty unwashed ULs are held for recovery. Washed stock remains the fallback.
4. **Detention-time measurement:** time spent at each node is recorded when an RTI departs, using the tag's arrival-step timestamp as an efficient representation of detention time.

The model's 20-UL daily screening capacity, 1-day recovery lead time, order lead times, demand generation, and network structure are unchanged.

Detention averages are calculated from completed node stays (RTIs departing a node during the horizon); RTIs still in a node at day 365 are right-censored and are not included in that completed-stay average.

## Important modelling boundary

The assignment's illustrated RFID fields are location, washed status, filled status, product, and detention time. The screening priority uses product history, not the model's hidden `broken` flag. Breakage remains detected during physical recovery; the traceability rule does not assume RFID can detect damage.

## Apply and run

From the repository root:

```powershell
python tools/apply_traceability_scenario.py
python -m unittest discover -s tests -v
```

Run the faithful random baseline and the RFID traceability scenario:

```powershell
python main.py --scenario baseline --seed 42
python main.py --scenario traceability --seed 42
```

Summarize the latest run:

```powershell
python analysis/summarize_screening.py
python analysis/summarize_fulfillment.py
python analysis/summarize_traceability.py
```

Each run creates a timestamped workbook with the existing sheets plus `Detention`. The `Screening` sheet also separates new-arrival screening from dirty backlog re-screening.

## Interpretation

The scenario is a proposed managerial decision rule, not an optimization and not proof of improvement. Task 2 will quantify its value against the baseline using multiple independent replications. A shared random seed improves repeatability, but because policy changes alter random-number consumption, it does not guarantee perfectly matched stochastic events between scenarios.
'''

if __name__ == '__main__':
    main()
