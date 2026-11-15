import os
from datetime import datetime

# Import constants and the model
from config import SIMULATION_STEPS
from model import CLSC_Model

if __name__ == "__main__":
    print("\nSimulation starting...\n")

    current_timestamp = datetime.now().strftime("%Y.%m.%d_%H.%M")
    run_folder = f"run_{current_timestamp}"
    os.makedirs(run_folder, exist_ok=True)

    model = CLSC_Model(results_dir=run_folder, run_timestamp=current_timestamp)

    for i in range(SIMULATION_STEPS):
        model.step()

        progress_pct = ((i + 1) / SIMULATION_STEPS) * 100
        bar_length = 70
        filled = int(bar_length * (i + 1) / SIMULATION_STEPS)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\r[{bar}] {progress_pct:.1f}% | Step (Day) {i + 1:3d}/{SIMULATION_STEPS}", end='', flush=True)

    print("\n\nSimulation completed.")
    model.export_to_excel()
