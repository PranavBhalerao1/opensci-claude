
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 2: Validate mean_gap computation
# ============================================================
print("=== VALIDATION: mean_gap recomputation ===")
gap_traj_recomputed = gap_traj.copy()
gap_traj_recomputed['mean_gap_check'] = (gap_traj['gap_seed42'] + gap_traj['gap_seed123']) / 2
discrepancies = gap_traj_recomputed[~np.isclose(gap_traj_recomputed['mean_gap'], gap_traj_recomputed['mean_gap_check'], atol=1e-4)]
print(f"  Discrepancies: {len(discrepancies)}")
print(f"  mean_gap range: {gap_traj['mean_gap'].min():.4f} to {gap_traj['mean_gap'].max():.4f}")
print(f"  All mean_gap > 0? {(gap_traj['mean_gap'] > 0).any()}")
print(f"  Max mean_gap: {gap_traj['mean_gap'].max():.4f} at epoch {gap_traj.loc[gap_traj['mean_gap'].idxmax(),'epoch']}")

# Key epochs
for ep in [5, 10, 20, 30]:
    row = gap_traj[gap_traj['epoch']==ep].iloc[0]
    print(f"  Epoch {ep:2d}: gap_42={row['gap_seed42']:.4f}, gap_123={row['gap_seed123']:.4f}, mean={row['mean_gap']:.4f}")
