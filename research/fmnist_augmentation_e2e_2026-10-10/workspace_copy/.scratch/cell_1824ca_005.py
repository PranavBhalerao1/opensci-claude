
import pandas as pd
import numpy as np

# ── Load combined metrics ──────────────────────────────────────────────────────
df = pd.read_csv('analysis/combined_metrics.csv')
print("combined_metrics.csv shape:", df.shape)

# ── Step 1: Separate augmented / non-augmented ────────────────────────────────
aug_df   = df[df['augmented'] == True ].copy()
noaug_df = df[df['augmented'] == False].copy()

# Merge on (seed, epoch)
merged = pd.merge(
    aug_df  [['seed','epoch','test_acc','train_loss','val_acc']].rename(
        columns={'test_acc':'test_acc_aug','train_loss':'train_loss_aug','val_acc':'val_acc_aug'}),
    noaug_df[['seed','epoch','test_acc','train_loss','val_acc']].rename(
        columns={'test_acc':'test_acc_noaug','train_loss':'train_loss_noaug','val_acc':'val_acc_noaug'}),
    on=['seed','epoch']
)
print("\nMerged shape:", merged.shape)
print("NaNs:", merged.isna().sum().sum())

# ── Compute per-seed accuracy gap ─────────────────────────────────────────────
merged['accuracy_gap'] = merged['test_acc_aug'] - merged['test_acc_noaug']

# Sanity-check a few values against raw CSVs
print("\n-- Spot checks against raw CSVs --")
spot_checks = [
    (42,  5,  88.60 - 91.30),   # aug ep5 seed42: 88.60?  noaug 91.30
    (42,  30, 91.28 - 92.65),
    (123, 5,  None),
    (123, 30, None),
]
for seed, ep, _ in [(42,5,None),(42,30,None),(123,5,None),(123,30,None)]:
    row = merged[(merged['seed']==seed) & (merged['epoch']==ep)]
    print(f"  seed={seed} ep={ep}: aug={row['test_acc_aug'].values[0]:.2f}  "
          f"noaug={row['test_acc_noaug'].values[0]:.2f}  "
          f"gap={row['accuracy_gap'].values[0]:.4f}")
