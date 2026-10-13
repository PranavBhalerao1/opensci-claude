
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj  = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats= pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 6: Also pull val_acc from combined_metrics for ep 5 & 30
# ============================================================
print("=== VAL_ACC at epochs 5 and 30 (from combined_metrics) ===")
for ep in [5, 30]:
    print(f"\n  Epoch {ep}:")
    for seed in [42, 123]:
        for aug_flag, label in [(False, "noaug"), (True, "aug")]:
            row = combined[(combined['seed']==seed) & (combined['augmented']==aug_flag) & (combined['epoch']==ep)]
            va = row['val_acc'].values[0]
            tl = row['train_loss'].values[0]
            ta = row['test_acc'].values[0]
            print(f"    seed={seed} {label}: train_loss={tl:.6f}, val_acc={va:.4f}%, test_acc={ta:.4f}%")

# Val_acc divergence proxy at epoch 5 (underfitting: both still high val_acc but similar; train_loss high)
print("\n=== DIVERGENCE PROXY SUMMARY ===")
# Epoch 5
r_noaug_s42_ep5  = combined[(combined['seed']==42)  & (combined['augmented']==False) & (combined['epoch']==5)].iloc[0]
r_aug_s42_ep5    = combined[(combined['seed']==42)  & (combined['augmented']==True)  & (combined['epoch']==5)].iloc[0]
r_noaug_s123_ep5 = combined[(combined['seed']==123) & (combined['augmented']==False) & (combined['epoch']==5)].iloc[0]
r_aug_s123_ep5   = combined[(combined['seed']==123) & (combined['augmented']==True)  & (combined['epoch']==5)].iloc[0]

print("Epoch 5 val_acc divergence (noaug - aug):")
print(f"  seed42:  noaug_val={r_noaug_s42_ep5['val_acc']:.2f}%, aug_val={r_aug_s42_ep5['val_acc']:.2f}%, diff={r_noaug_s42_ep5['val_acc']-r_aug_s42_ep5['val_acc']:.2f}pp")
print(f"  seed123: noaug_val={r_noaug_s123_ep5['val_acc']:.2f}%, aug_val={r_aug_s123_ep5['val_acc']:.2f}%, diff={r_noaug_s123_ep5['val_acc']-r_aug_s123_ep5['val_acc']:.2f}pp")

# Epoch 30
r_noaug_s42_ep30  = combined[(combined['seed']==42)  & (combined['augmented']==False) & (combined['epoch']==30)].iloc[0]
r_aug_s42_ep30    = combined[(combined['seed']==42)  & (combined['augmented']==True)  & (combined['epoch']==30)].iloc[0]
r_noaug_s123_ep30 = combined[(combined['seed']==123) & (combined['augmented']==False) & (combined['epoch']==30)].iloc[0]
r_aug_s123_ep30   = combined[(combined['seed']==123) & (combined['augmented']==True)  & (combined['epoch']==30)].iloc[0]

print("Epoch 30 val_acc divergence (noaug - aug):")
print(f"  seed42:  noaug_val={r_noaug_s42_ep30['val_acc']:.2f}%, aug_val={r_aug_s42_ep30['val_acc']:.2f}%, diff={r_noaug_s42_ep30['val_acc']-r_aug_s42_ep30['val_acc']:.2f}pp")
print(f"  seed123: noaug_val={r_noaug_s123_ep30['val_acc']:.2f}%, aug_val={r_aug_s123_ep30['val_acc']:.2f}%, diff={r_noaug_s123_ep30['val_acc']-r_aug_s123_ep30['val_acc']:.2f}pp")

# No-aug train_loss trajectory
print("\nNo-aug train_loss (underfitting → fitting):")
for ep in [1, 5, 10, 20, 30]:
    s42  = combined[(combined['seed']==42)  & (combined['augmented']==False) & (combined['epoch']==ep)]['train_loss'].values[0]
    s123 = combined[(combined['seed']==123) & (combined['augmented']==False) & (combined['epoch']==ep)]['train_loss'].values[0]
    print(f"  ep={ep:2d}: s42={s42:.6f}, s123={s123:.6f}, mean={(s42+s123)/2:.6f}")
