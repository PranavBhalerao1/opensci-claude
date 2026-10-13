
import pandas as pd
import numpy as np

# ── Load combined metrics ──────────────────────────────────────────────────────
df = pd.read_csv('analysis/combined_metrics.csv')

aug_df   = df[df['augmented'] == True ].copy()
noaug_df = df[df['augmented'] == False].copy()

merged = pd.merge(
    aug_df  [['seed','epoch','test_acc','train_loss','val_acc']].rename(
        columns={'test_acc':'test_acc_aug','train_loss':'train_loss_aug','val_acc':'val_acc_aug'}),
    noaug_df[['seed','epoch','test_acc','train_loss','val_acc']].rename(
        columns={'test_acc':'test_acc_noaug','train_loss':'train_loss_noaug','val_acc':'val_acc_noaug'}),
    on=['seed','epoch']
)
merged['accuracy_gap'] = merged['test_acc_aug'] - merged['test_acc_noaug']

# ── Step 2: Pivot to wide format for gap_trajectory ───────────────────────────
pivot = merged.pivot(index='epoch', columns='seed', values='accuracy_gap').reset_index()
pivot.columns.name = None
pivot = pivot.rename(columns={42:'gap_seed42', 123:'gap_seed123'})
pivot['mean_gap'] = pivot[['gap_seed42','gap_seed123']].mean(axis=1)
pivot = pivot.sort_values('epoch').reset_index(drop=True)

print("Gap trajectory (all 30 rows):")
print(pivot.to_string())
print(f"\nShape: {pivot.shape}")
print(f"NaN count: {pivot.isna().sum().sum()}")
