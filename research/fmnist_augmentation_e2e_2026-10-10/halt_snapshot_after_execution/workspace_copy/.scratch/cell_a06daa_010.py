
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 3: Apply crossover criterion (mean_gap > 0 for ≥ 3 consecutive epochs)
# ============================================================
print("=== CROSSOVER CRITERION: mean_gap > 0 for ≥ 3 consecutive epochs ===")

mean_gaps = gap_traj['mean_gap'].values   # epochs 1-30
epochs    = gap_traj['epoch'].values

crossover_epoch = None
for i in range(len(epochs) - 2):   # need at least 3 ahead
    ep = epochs[i]
    if ep > 28:                     # can't have 3 consecutive ending by ep30
        break
    if mean_gaps[i] > 0 and mean_gaps[i+1] > 0 and mean_gaps[i+2] > 0:
        crossover_epoch = int(ep)
        print(f"  Crossover found at epoch {crossover_epoch}")
        print(f"  Consecutive mean_gaps: {mean_gaps[i]:.4f}, {mean_gaps[i+1]:.4f}, {mean_gaps[i+2]:.4f}")
        break

if crossover_epoch is None:
    print("  No crossover within 30 epochs (no 3 consecutive epochs with mean_gap > 0 found up to epoch 28)")
    print(f"  Closest: epoch 29 mean_gap={mean_gaps[epochs==29][0]:.4f} (still negative; also only 2 remaining epochs)")
    crossover_statement = "No crossover within 30 epochs"
else:
    crossover_statement = f"Crossover at epoch {crossover_epoch}"

print(f"\n  Crossover statement: '{crossover_statement}'")
