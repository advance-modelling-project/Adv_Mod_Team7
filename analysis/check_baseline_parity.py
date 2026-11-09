"""Compare the professor's standalone model with the modular baseline.

This is an explicit parity audit, NOT an RFID-vs-baseline experiment.
In particular, both models are created in the same Python process and seeded
separately to avoid different interpreter hash salts.

Usage from repository root:
    python analysis/check_baseline_parity.py --days 5 --seed 42

For a stronger (slower) check:
    python analysis/check_baseline_parity.py --days 365 --seed 42

No simulation workbooks are overwritten or generated.
"""

import argparse
import gc
import importlib.util
import random
from pathlib import Path

import pandas as pd

from config import SimulationConfig
from model import CLSC_Model as ModularModel

PREFIXES = ('Stock|', 'Flow|', 'Backorders|')


def run(cls, kwargs, days, seed):
    random.seed(seed)
    model = cls(**kwargs)
    rng_after_initialization = random.getstate()
    samples = []
    for _ in range(days):
        model.step()
        samples.append(random.getstate())
    recorded = model.datacollector.get_model_vars_dataframe()
    names = sorted(c for c in recorded.columns if c.startswith(PREFIXES))
    values = recorded[names].copy().reset_index(drop=True)
    del model
    gc.collect()
    return values, rng_after_initialization, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=5)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--reference', type=Path, default=Path('Assignment_code_baseline.py'))
    args = parser.parse_args()
    if args.days < 1 or args.days > 365:
        parser.error('--days must be 1 to 365')
    if not args.reference.is_file():
        parser.error(f'Professor reference file not found: {args.reference}')

    spec = importlib.util.spec_from_file_location('professor_clsc_reference', args.reference.resolve())
    professor_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(professor_module)

    print('Professor reference:', args.reference.resolve(), flush=True)
    print('Days:', args.days, 'Seed:', args.seed, flush=True)
    print('Running professor reference...', flush=True)
    reference, ref_initial, ref_rng = run(
        professor_module.CLSC_Model, {}, args.days, args.seed
    )
    print('Running modular baseline (RFID disabled)...', flush=True)
    modular, mod_initial, mod_rng = run(
        ModularModel, {'config': SimulationConfig(TRACEABILITY_ENABLED=False)},
        args.days, args.seed
    )

    print('Same RNG state after initialization:', ref_initial == mod_initial)
    first_rng_difference = next((i for i, (a,b) in enumerate(zip(ref_rng,mod_rng), 1) if a!=b), None)
    print('First differing RNG state after day:', first_rng_difference or 'none')

    ref_cols, mod_cols = set(reference.columns), set(modular.columns)
    if ref_cols != mod_cols:
        print('Only in professor reference:', sorted(ref_cols - mod_cols))
        print('Only in modular baseline:', sorted(mod_cols - ref_cols))
        raise SystemExit('PARITY FAIL: different metric columns')
    if len(reference) != len(modular):
        raise SystemExit(f'PARITY FAIL: row count {len(reference)} vs {len(modular)}')
    different = reference.ne(modular)
    differing = different.stack()
    bad = differing[differing]
    if bad.empty and first_rng_difference is None and ref_initial == mod_initial:
        print(f'PARITY PASS: all {len(reference)} daily states match, including stock, flows and backorders.')
        return

    if not bad.empty:
        print('PARITY FAIL: first 15 differences (row index is day 0..N):')
        for (row,col) in list(bad.index[:15]):
            print(f'  Day {row}: {col}: professor={reference.at[row,col]} modular={modular.at[row,col]}')
        print('First differing recorded day:', bad.index[0][0])
    else:
        print('All recorded stock/flow/backorder values match, but RNG states differ.')
    raise SystemExit('PARITY NOT ESTABLISHED: investigate differences before relying on a baseline comparison.')


if __name__ == '__main__':
    main()
