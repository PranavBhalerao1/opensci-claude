
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 1: Validate gap_trajectory against combined_metrics raw
# ============================================================
print("=== VALIDATION: Recompute gaps from raw combined_metrics ===")

# Pivot to get aug and noaug side by side
noaug = combined[combined['augmented'] == False].set_index(['seed','epoch'])
aug   = combined[combined['augmented'] == True].set_index(['seed','epoch'])

# Compute accuracy_gap = test_acc_aug - test_acc_noaug
gap_df = (aug['test_acc'] - noaug['test_acc']).reset_index()
gap_df.columns = ['seed', 'epoch', 'accuracy_gap']
print(gap_df.head(10))

# Compare with gap_trajectory for epoch 5
for seed in [42, 123]:
    for ep in [5, 10, 20, 30]:
        raw_val = gap_df[(gap_df['seed']==seed) & (gap_df['epoch']==ep)]['accuracy_gap'].values[0]
        col = f'gap_seed{seed}'
        traj_val = gap_traj[gap_traj['epoch']==ep][col].values[0]
        match = np.isclose(raw_val, traj_val, atol=1e-4)
        print(f"  seed={seed} ep={ep}: raw={raw_val:.4f}, trajectory={traj_val:.4f}, match={match}")
