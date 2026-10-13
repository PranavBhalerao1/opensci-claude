
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

# ── gap_trajectory ────────────────────────────────────────────────────────────
pivot = merged.pivot(index='epoch', columns='seed', values='accuracy_gap').reset_index()
pivot.columns.name = None
pivot = pivot.rename(columns={42:'gap_seed42', 123:'gap_seed123'})
pivot['mean_gap'] = pivot[['gap_seed42','gap_seed123']].mean(axis=1)
gap_traj = pivot.sort_values('epoch')[['epoch','gap_seed42','gap_seed123','mean_gap']].reset_index(drop=True)

# ── checkpoint_stats (epochs 5, 10, 20, 30) ───────────────────────────────────
ckpt_epochs = [5, 10, 20, 30]
ckpt_rows = []

for ep in ckpt_epochs:
    row_merged = merged[merged['epoch'] == ep]
    
    # Seed 42
    r42 = row_merged[row_merged['seed'] == 42].iloc[0]
    # Seed 123
    r123 = row_merged[row_merged['seed'] == 123].iloc[0]
    
    gap42  = r42['accuracy_gap']
    gap123 = r123['accuracy_gap']
    mean_gap = (gap42 + gap123) / 2
    
    ckpt_rows.append({
        'epoch'             : ep,
        'noaug_s42_test'    : r42['test_acc_noaug'],
        'aug_s42_test'      : r42['test_acc_aug'],
        'gap_s42'           : round(gap42, 4),
        'noaug_s123_test'   : r123['test_acc_noaug'],
        'aug_s123_test'     : r123['test_acc_aug'],
        'gap_s123'          : round(gap123, 4),
        'mean_gap'          : round(mean_gap, 4),
        'noaug_s42_trainloss'  : r42['train_loss_noaug'],
        'aug_s42_trainloss'    : r42['train_loss_aug'],
        'noaug_s123_trainloss' : r123['train_loss_noaug'],
        'aug_s123_trainloss'   : r123['train_loss_aug'],
    })

ckpt_df = pd.DataFrame(ckpt_rows)

print("=== checkpoint_stats.csv ===")
print(ckpt_df.to_string(index=False))
print(f"\nShape: {ckpt_df.shape}")
print(f"NaN count: {ckpt_df.isna().sum().sum()}")
print("\nColumns:", ckpt_df.columns.tolist())
