
import pandas as pd
import numpy as np

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

# ── gap_trajectory ─────────────────────────────────────────────────────────────
pivot = merged.pivot(index='epoch', columns='seed', values='accuracy_gap').reset_index()
pivot.columns.name = None
pivot = pivot.rename(columns={42:'gap_seed42', 123:'gap_seed123'})
pivot['mean_gap'] = pivot[['gap_seed42','gap_seed123']].mean(axis=1)
gap_traj = pivot.sort_values('epoch')[['epoch','gap_seed42','gap_seed123','mean_gap']].reset_index(drop=True)

# ── Step 3: Crossover analysis ─────────────────────────────────────────────────
print("=== Crossover Analysis ===")
print("Mean gap trajectory:")
for _, row in gap_traj.iterrows():
    flag = " <<" if row['mean_gap'] > 0 else ""
    print(f"  Epoch {int(row['epoch']):2d}: mean_gap={row['mean_gap']:+.4f}{flag}")

# Find first epoch where mean_gap > 0 for >= 3 consecutive epochs
crossover = None
for i in range(len(gap_traj)-2):
    e1 = gap_traj.iloc[i]['mean_gap']
    e2 = gap_traj.iloc[i+1]['mean_gap']
    e3 = gap_traj.iloc[i+2]['mean_gap']
    if e1 > 0 and e2 > 0 and e3 > 0:
        crossover = int(gap_traj.iloc[i]['epoch'])
        print(f"\n✓ Crossover found at epoch {crossover}")
        break

if crossover is None:
    print("\n✗ No crossover found within 30 epochs — mean_gap never positive for 3 consecutive epochs.")
    print("  → Epoch-5 regime classification: underfitting-penalty-confirmed")

# Epoch-5 mean_gap
ep5_mean_gap = gap_traj.loc[gap_traj['epoch']==5,'mean_gap'].values[0]
print(f"\nEpoch-5 mean_gap = {ep5_mean_gap:.4f} pp")
