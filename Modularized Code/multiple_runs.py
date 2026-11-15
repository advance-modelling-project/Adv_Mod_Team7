import os
import random
import csv
from datetime import datetime

# 直接从 config 导入，与 main.py 保持一致
from config import SIMULATION_STEPS
from model import CLSC_Model

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

    # 生成并记录随机种子
    random.seed(BASE_SEED)
    run_seeds = [random.randint(0, 999999) for _ in range(NUM_REPLICATIONS)]

    seed_log_path = os.path.join(run_folder, "seeds_log.csv")
    with open(seed_log_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Replication_ID", "Seed"])
        for run_id, seed in enumerate(run_seeds):
            writer.writerow([run_id + 1, seed])

    # 执行多次模拟
    for run_id in range(NUM_REPLICATIONS):
        current_seed = run_seeds[run_id]
        random.seed(current_seed)

        print(f"\n--- Replication {run_id + 1}/{NUM_REPLICATIONS} | Seed: {current_seed} ---")

        model = CLSC_Model(results_dir=run_folder, run_timestamp=f"{current_timestamp}_rep{run_id + 1}")

        for step in range(SIMULATION_STEPS):
            model.step()

            # 与 main.py 对齐的进度条样式
            progress_pct = ((step + 1) / SIMULATION_STEPS) * 100
            bar_length = 70
            filled = int(bar_length * (step + 1) / SIMULATION_STEPS)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r[{bar}] {progress_pct:.1f}% | Step (Day) {step + 1:3d}/{SIMULATION_STEPS}", end='', flush=True)

        print()
        model.export_to_excel()

    print("\n\nAll replications completed successfully.")