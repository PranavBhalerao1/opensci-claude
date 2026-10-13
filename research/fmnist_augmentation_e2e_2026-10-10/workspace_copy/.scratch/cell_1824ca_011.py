
import pandas as pd
import numpy as np

# ── Final comprehensive validation against raw CSVs ───────────────────────────
print("=== Final validation against raw per-epoch CSVs ===\n")

raw_noaug_42  = pd.read_csv('data/metrics_seed42_noaug.csv')
raw_aug_42    = pd.read_csv('data/metrics_seed42_aug.csv')
raw_noaug_123 = pd.read_csv('data/metrics_seed123_noaug.csv')
raw_aug_123   = pd.read_csv('data/metrics_seed123_aug.csv')

# Determine the epoch column name (first col is comment-header)
def get_col(df):
    """Return epoch, train_loss, val_acc, test_acc arrays (0-indexed epoch = row+1)."""
    # columns: [comment_col, train_loss, train_acc, val_acc, test_acc]
    return df.iloc[:, 1].values, df.iloc[:, 3].values, df.iloc[:, 4].values

# Parse each raw CSV: epoch 1 = row 0
def parse_raw(df):
    epochs     = (np.arange(len(df)) + 1).astype(int)
    train_loss = df.iloc[:, 1].values
    val_acc    = df.iloc[:, 3].values
    test_acc   = df.iloc[:, 4].values
    return pd.DataFrame({'epoch': epochs, 'train_loss': train_loss,
                         'val_acc': val_acc, 'test_acc': test_acc})

rna42  = parse_raw(raw_noaug_42)
ra42   = parse_raw(raw_aug_42)
rna123 = parse_raw(raw_noaug_123)
ra123  = parse_raw(raw_aug_123)

gap_traj  = pd.read_csv('analysis/gap_trajectory.csv')
ckpt_df   = pd.read_csv('analysis/checkpoint_stats.csv')

# Spot-check all 4 checkpoint epochs, both seeds, both metrics
errors = []
for ep in [5, 10, 20, 30]:
    # Seed 42 noaug test_acc
    raw_val = rna42.loc[rna42['epoch']==ep, 'test_acc'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'noaug_s42_test'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} noaug_s42_test:  raw={raw_val:.2f}  csv={csv_val:.2f}  {'✓' if match else '✗ MISMATCH'}")
    if not match: errors.append(f"Ep{ep} noaug_s42_test")

    # Seed 42 aug test_acc
    raw_val = ra42.loc[ra42['epoch']==ep, 'test_acc'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'aug_s42_test'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} aug_s42_test:    raw={raw_val:.2f}  csv={csv_val:.2f}  {'✓' if match else '✗ MISMATCH'}")
    if not match: errors.append(f"Ep{ep} aug_s42_test")

    # Seed 123 noaug test_acc
    raw_val = rna123.loc[rna123['epoch']==ep, 'test_acc'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'noaug_s123_test'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} noaug_s123_test: raw={raw_val:.2f}  csv={csv_val:.2f}  {'✓' if match else '✗ MISMATCH'}")
    if not match: errors.append(f"Ep{ep} noaug_s123_test")

    # Seed 123 aug test_acc
    raw_val = ra123.loc[ra123['epoch']==ep, 'test_acc'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'aug_s123_test'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} aug_s123_test:   raw={raw_val:.2f}  csv={csv_val:.2f}  {'✓' if match else '✗ MISMATCH'}")
    if not match: errors.append(f"Ep{ep} aug_s123_test")
    
    # Train loss seed 42 noaug
    raw_val = rna42.loc[rna42['epoch']==ep, 'train_loss'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'noaug_s42_trainloss'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} noaug_s42_trainloss: raw={raw_val:.6f}  csv={csv_val:.6f}  {'✓' if match else '✗ MISMATCH'}")

    # Train loss seed 42 aug
    raw_val = ra42.loc[ra42['epoch']==ep, 'train_loss'].values[0]
    csv_val = ckpt_df.loc[ckpt_df['epoch']==ep, 'aug_s42_trainloss'].values[0]
    match = abs(raw_val - csv_val) < 1e-6
    print(f"  Ep{ep:2d} aug_s42_trainloss:   raw={raw_val:.6f}  csv={csv_val:.6f}  {'✓' if match else '✗ MISMATCH'}")
    print()

# Also spot-check gap_trajectory for all 30 epochs
print("=== Validating gap_trajectory against raw CSVs (all 30 epochs) ===")
traj_errors = 0
for ep in range(1, 31):
    raw_gap42  = (ra42.loc[ra42['epoch']==ep,'test_acc'].values[0] 
                  - rna42.loc[rna42['epoch']==ep,'test_acc'].values[0])
    raw_gap123 = (ra123.loc[ra123['epoch']==ep,'test_acc'].values[0] 
                  - rna123.loc[rna123['epoch']==ep,'test_acc'].values[0])
    raw_mean   = (raw_gap42 + raw_gap123) / 2

    csv_gap42  = gap_traj.loc[gap_traj['epoch']==ep,'gap_seed42'].values[0]
    csv_gap123 = gap_traj.loc[gap_traj['epoch']==ep,'gap_seed123'].values[0]
    csv_mean   = gap_traj.loc[gap_traj['epoch']==ep,'mean_gap'].values[0]

    ok = abs(raw_gap42-csv_gap42)<1e-4 and abs(raw_gap123-csv_gap123)<1e-4 and abs(raw_mean-csv_mean)<1e-4
    if not ok:
        print(f"  MISMATCH ep={ep}: raw=({raw_gap42:.4f},{raw_gap123:.4f},{raw_mean:.4f}) "
              f"csv=({csv_gap42:.4f},{csv_gap123:.4f},{csv_mean:.4f})")
        traj_errors += 1

if traj_errors == 0:
    print(f"  All 30 epoch gap values validated ✓")
else:
    print(f"  {traj_errors} mismatches found!")

if errors:
    print(f"\nFAILED checks: {errors}")
else:
    print("\n✓ All raw CSV spot-checks passed!")
