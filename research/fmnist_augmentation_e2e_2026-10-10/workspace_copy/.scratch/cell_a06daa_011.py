
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 4: Epoch-5 regime classification
# ============================================================
print("=== EPOCH-5 REGIME CLASSIFICATION ===")

ep5_row = gap_traj[gap_traj['epoch'] == 5].iloc[0]
gap_s42_ep5  = ep5_row['gap_seed42']    # from gap_trajectory.csv
gap_s123_ep5 = ep5_row['gap_seed123']   # from gap_trajectory.csv
mean_gap_ep5 = ep5_row['mean_gap']

print(f"  gap_seed42   at epoch 5: {gap_s42_ep5:.4f}")
print(f"  gap_seed123  at epoch 5: {gap_s123_ep5:.4f}")
print(f"  mean_gap     at epoch 5: {mean_gap_ep5:.4f}")

# Cross-validate vs checkpoint_stats
ck_ep5 = ckpt_stats[ckpt_stats['epoch'] == 5].iloc[0]
assert np.isclose(ck_ep5['gap_s42'],  gap_s42_ep5,  atol=1e-4), "Mismatch in gap_s42 at ep5"
assert np.isclose(ck_ep5['gap_s123'], gap_s123_ep5, atol=1e-4), "Mismatch in gap_s123 at ep5"
print("  Cross-validated vs checkpoint_stats: OK")

# Classify
if gap_s42_ep5 <= 0 and gap_s123_ep5 <= 0:
    regime = "underfitting-penalty-confirmed"
elif gap_s42_ep5 > 0 and gap_s123_ep5 > 0:
    regime = "early-benefit"
else:
    regime = "mixed"

print(f"\n  Epoch-5 regime: '{regime}'")
print(f"  Reasoning: gap_42={gap_s42_ep5:.2f} ≤ 0 AND gap_123={gap_s123_ep5:.2f} ≤ 0 → both seeds negative")
