"""Restore professor's Pooler stock retrieval in non-RFID (baseline) mode.

Designed for the user's Task 1 v3 branch. Does not replace the RFID
policy, the order tracker, instrumentation, or the dashboard.

From repository root:
    python tools/apply_baseline_parity_v1.py

The write is atomic and guarded by source checks. The originals are backed up
under tools/.baseline_parity_backup/. No files are written if checks fail.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path.cwd()
FILE = ROOT / 'agents.py'
BACKUPS = ROOT / 'tools' / '.baseline_parity_backup'
TAG = '    # BASELINE_PARITY_V1: faithful Pooler UL selection, traceability unchanged'

# This method follows the actual corrected assignment's Pooler_Agent.extract_uls
# including the subtle distinction between random sampling when stock is
# sufficient and deterministic stock exhaustion when total stock is inadequate.
METHOD = '''    def _assignment_baseline_extract_uls(self, crate_type, needs_washed, quantity_uls):
        """Exact assignment baseline's UL selection and RNG calls.

        A producer order with needs_washed=True can use only washed loads.
        A flexible order prefers unwashed loads and uses washed as fallback.
        This routine intentionally preserves random.sample branches and
        stock-exhaustion behavior; it is invoked ONLY with RFID disabled.
        """
        if needs_washed is True:
            primary_stock = self.washed_stock_pool[crate_type]
            secondary_stock = []
        else:
            primary_stock = self.unwashed_stock_pool[crate_type]
            secondary_stock = self.washed_stock_pool[crate_type]

        primary_available = len(primary_stock)
        secondary_available = len(secondary_stock)
        total_available = primary_available + secondary_available
        selected_uls = []

        if total_available >= quantity_uls:
            if primary_available >= quantity_uls:
                selected_uls = random.sample(primary_stock, quantity_uls)
                for ul in selected_uls:
                    primary_stock.remove(ul)
            else:
                selected_primary = list(primary_stock)
                primary_stock.clear()
                needed = quantity_uls - primary_available
                selected_secondary = random.sample(secondary_stock, needed)
                for ul in selected_secondary:
                    secondary_stock.remove(ul)
                selected_uls = selected_primary + selected_secondary
        else:
            selected_uls = list(primary_stock) + list(secondary_stock)
            primary_stock.clear()
            if secondary_stock:
                secondary_stock.clear()
        return selected_uls

'''

PREFIX = '''        # BASELINE_PARITY_V1: use the actual assignment baseline selection rule.
        if not self.model.config.TRACEABILITY_ENABLED:
            return self._assignment_baseline_extract_uls(
                crate_type, needs_washed, quantity_uls
            )

'''


def find_method(source: str, cls: str, meth: str):
    tree = ast.parse(source)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls]
    if len(classes) != 1:
        raise RuntimeError(f'Expected one class {cls}, found {len(classes)}')
    matches = [node for node in classes[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == meth]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one method {cls}.{meth}, found {len(matches)}')
    return matches[0]


def apply():
    if not FILE.is_file():
        raise RuntimeError('Run from repository root: agents.py not found')
    original = FILE.read_text(encoding='utf-8')
    if TAG in original or 'BASELINE_PARITY_V1:' in original:
        raise RuntimeError('Already patched. Refusing to apply a second time.')
    if 'TRACEABILITY_ENABLED' not in original:
        raise RuntimeError('Task 1 scenario switch is missing; this patch expects the v3 branch.')
    if 'import random' not in original:
        raise RuntimeError('Expected random module import in agents.py')
    pool = find_method(original, 'Pooler_Agent', 'extract_uls')
    if 'TRACEABILITY_ENABLED' not in ast.get_source_segment(original, pool):
        raise RuntimeError('Expected v3 Pooler.extract_uls with a traceability branch')
    if 'self._take_uls' not in ast.get_source_segment(original, pool):
        raise RuntimeError('Unrecognized Pooler.extract_uls: _take_uls missing')
    producer = find_method(original, 'Producer_Agent', 'extract_rtis')
    producer_source = ast.get_source_segment(original, producer)
    if 'random.sample' not in producer_source or 'TRACEABILITY_ENABLED' not in producer_source:
        raise RuntimeError('Producer baseline retrieval must already use random.sample')
    screening = find_method(original, 'Pooler_Agent', 'screen_uls')
    screening_source = ast.get_source_segment(original, screening)
    if 'random.sample' not in screening_source or 'TRACEABILITY_ENABLED' not in screening_source:
        raise RuntimeError('Baseline screening must already use random.sample')

    lines = original.splitlines(keepends=True)
    if not lines[pool.lineno - 1].startswith('    def extract_uls('):
        raise RuntimeError('Unexpected method indentation; no change made')
    new_lines = (
        lines[:pool.lineno - 1]
        + [TAG + '\n', METHOD]
        + [lines[pool.lineno - 1]]
        + [PREFIX]
        + lines[pool.lineno:]
    )
    patched = ''.join(new_lines)
    compile(patched, str(FILE), 'exec')
    find_method(patched, 'Pooler_Agent', '_assignment_baseline_extract_uls')

    BACKUPS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(original.encode('utf-8')).hexdigest()[:12]
    backup = BACKUPS / f'agents.py.before_baseline_parity_{digest}'
    if not backup.exists():
        shutil.copy2(FILE, backup)
    fd, name = tempfile.mkstemp(prefix='.agents-parity-', dir=FILE.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(patched)
        os.replace(name, FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print('Applied professor baseline Pooler selection to baseline mode only.')
    print('RFID traceability selection and KPI instrumentation left unchanged.')
    print('Original backed up:', backup)
    print('Next: python -m unittest discover -s tests -v')
    print('Then: python analysis/check_baseline_parity.py --days 5 --seed 42')


if __name__ == '__main__':
    apply()
