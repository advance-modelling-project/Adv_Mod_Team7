import os
import random
import csv
from datetime import datetime
from config import SimulationConfig
from model import CLSC_Model

# 2. 实例化配置对象
config_params = SimulationConfig()

# =============================================================================
# RUN PARAMETERS
# =============================================================================
NUM_REPLICATIONS = 30
BASE_SEED = 42

if __name__ == "__main__":
    print(f"\nStarting Monte Carlo Simulation: {NUM_REPLICATIONS} replications...\n")

    current_timestamp = datetime.now().strftime("%Y.%m.%d_%H.%M")
    run_folder = f"run_{current_timestamp}"
    os.makedirs(run_folder, exist_ok=True)

    random.seed(BASE_SEED)
    run_seeds = [random.randint(0, 999999) for _ in range(NUM_REPLICATIONS)]

    seed_log_path = os.path.join(run_folder, "seeds_log.csv")
    with open(seed_log_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Replication_ID", "Seed"])
        for run_id, seed in enumerate(run_seeds):
            writer.writerow([run_id + 1, seed])

    for run_id in range(NUM_REPLICATIONS):
        current_seed = run_seeds[run_id]
        random.seed(current_seed)

        print(f"\n--- Replication {run_id + 1}/{NUM_REPLICATIONS} | Seed: {current_seed} ---")

        # 实例化模型时，可能也需要把 config_params 传进去（取决于你 model.py 怎么接收）
        model = CLSC_Model(results_dir=run_folder, run_timestamp=f"{current_timestamp}_rep{run_id + 1}")

        # 3. 调用时加上 config_params. 前缀
        for step in range(config_params.SIMULATION_STEPS):
            model.step()

            progress_pct = ((step + 1) / config_params.SIMULATION_STEPS) * 100
            bar_length = 50
            filled = int(bar_length * (step + 1) / config_params.SIMULATION_STEPS)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r[{bar}] {progress_pct:.1f}% | Step {step + 1:3d}/{config_params.SIMULATION_STEPS}", end='',
                  flush=True)

        print()
        model.export_to_excel()

    print("\n\nAll replications completed successfully.")