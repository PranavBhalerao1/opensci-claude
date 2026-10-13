
import pandas as pd
import numpy as np

combined = pd.read_csv("analysis/combined_metrics.csv")
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

# ============================================================
# STEP 5: Train-val divergence evidence at epochs 5 and 30
# ============================================================
print("=== TRAIN-VAL DIVERGENCE EVIDENCE ===")

for ep in [5, 30]:
    ck_row = ckpt_stats[ckpt_stats['epoch'] == ep].iloc[0]
    print(f"\n  -- Epoch {ep} --")
    
    # Train loss (from checkpoint_stats)
    noaug_s42_tl  = ck_row['noaug_s42_trainloss']
    aug_s42_tl    = ck_row['aug_s42_trainloss']
    noaug_s123_tl = ck_row['noaug_s123_trainloss']
    aug_s123_tl   = ck_row['aug_s123_trainloss']
    
    # Test acc (from checkpoint_stats)
    noaug_s42_ta  = ck_row['noaug_s42_test']
    aug_s42_ta    = ck_row['aug_s42_test']
    noaug_s123_ta = ck_row['noaug_s123_test']
    aug_s123_ta   = ck_row['aug_s123_test']
    
    # Cross-validate train_loss vs combined_metrics
    for seed, aug_flag, expected_tl, label in [
        (42,  False, noaug_s42_tl,  "noaug_s42"),
        (42,  True,  aug_s42_tl,    "aug_s42"),
        (123, False, noaug_s123_tl, "noaug_s123"),
        (123, True,  aug_s123_tl,   "aug_s123"),
    ]:
        raw_tl = combined[(combined['seed']==seed) & (combined['augmented']==aug_flag) & (combined['epoch']==ep)]['train_loss'].values[0]
        match = np.isclose(raw_tl, expected_tl, atol=1e-6)
        print(f"    {label}: train_loss={expected_tl:.6f} (raw={raw_tl:.6f}, match={match})")
    
    # Cross-validate test_acc vs combined_metrics
    for seed, aug_flag, expected_ta, label in [
        (42,  False, noaug_s42_ta,  "noaug_s42"),
        (42,  True,  aug_s42_ta,    "aug_s42"),
        (123, False, noaug_s123_ta, "noaug_s123"),
        (123, True,  aug_s123_ta,   "aug_s123"),
    ]:
        raw_ta = combined[(combined['seed']==seed) & (combined['augmented']==aug_flag) & (combined['epoch']==ep)]['test_acc'].values[0]
        match = np.isclose(raw_ta, expected_ta, atol=1e-4)
        print(f"    {label}: test_acc={expected_ta:.4f}% (raw={raw_ta:.4f}%, match={match})")
    
    # Divergence summary
    delta_tl_s42  = aug_s42_tl  - noaug_s42_tl
    delta_tl_s123 = aug_s123_tl - noaug_s123_tl
    mean_delta_tl = (delta_tl_s42 + delta_tl_s123) / 2
    mean_noaug_tl = (noaug_s42_tl + noaug_s123_tl) / 2
    mean_aug_tl   = (aug_s42_tl   + aug_s123_tl)   / 2
    mean_noaug_ta = (noaug_s42_ta + noaug_s123_ta) / 2
    mean_aug_ta   = (aug_s42_ta   + aug_s123_ta)   / 2
    
    print(f"    Δtrain_loss (aug−noaug): s42={delta_tl_s42:.6f}, s123={delta_tl_s123:.6f}, mean={mean_delta_tl:.6f}")
    print(f"    Mean noaug train_loss: {mean_noaug_tl:.6f}   Mean aug train_loss: {mean_aug_tl:.6f}")
    print(f"    Mean noaug test_acc:   {mean_noaug_ta:.4f}%  Mean aug test_acc:  {mean_aug_ta:.4f}%")
