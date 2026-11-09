import argparse
import os
import random
from datetime import datetime
from config import SimulationConfig
from model import CLSC_Model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Team 7 closed-loop supply-chain simulation.")
    parser.add_argument("--scenario", choices=("baseline", "traceability"), default="baseline")
    parser.add_argument("--seed", type=int, default=None, help="Optional Python random seed for reproducibility.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    config = SimulationConfig(TRACEABILITY_ENABLED=(args.scenario == "traceability"))
    current_timestamp = datetime.now().strftime("%Y.%m.%d_%H.%M")
    run_folder = f"run_{args.scenario}_{current_timestamp}"
    os.makedirs(run_folder, exist_ok=True)

    print(f"\nSimulation starting — scenario: {args.scenario}; seed: {args.seed}\n")
    model = CLSC_Model(config=config, results_dir=run_folder, run_timestamp=current_timestamp)

    for i in range(config.SIMULATION_STEPS):
        model.step()
        progress_pct = ((i + 1) / config.SIMULATION_STEPS) * 100
        filled = int(70 * (i + 1) / config.SIMULATION_STEPS)
        print(f"\r[{'█' * filled}{'░' * (70 - filled)}] {progress_pct:.1f}% | Step (Day) {i + 1:3d}/{config.SIMULATION_STEPS}", end="", flush=True)

    print("\n\nSimulation completed.")
    model.export_to_excel()
