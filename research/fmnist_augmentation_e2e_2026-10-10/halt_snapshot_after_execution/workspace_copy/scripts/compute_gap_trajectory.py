"""
T3.2 — Accuracy Gap Trajectory & Checkpoint Statistics
=======================================================
Inputs : analysis/combined_metrics.csv
Outputs: analysis/gap_trajectory.csv   (30 rows)
         analysis/checkpoint_stats.csv  (4 rows)

Provenance: raw training CSVs in data/metrics_seed{42,123}_{aug,noaug}.csv
            generated 2026-10-10 on Fashion-MNIST (CUDA, 30-epoch CNN training)
"""

import os
import pandas as pd
import numpy as np

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/combined_metrics.csv')
assert df.shape == (120, 6), f"Unexpected shape: {df.shape}"
assert df.isna().sum().sum() == 0

aug_df   = df[df['augmented'] == True ].copy()
noaug_df = df[df['augmented'] == False].copy()

# ── Merge on (seed, epoch) ────────────────────────────────────────────────────
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

# ── checkpoint_stats ─────────────────────────────────────────────────────────
ckpt_epochs = [5, 10, 20, 30]
ckpt_rows = []
for ep in ckpt_epochs:
    row_merged = merged[merged['epoch'] == ep]
    r42  = row_merged[row_merged['seed'] == 42].iloc[0]
    r123 = row_merged[row_merged['seed'] == 123].iloc[0]
    gap42  = r42['accuracy_gap']
    gap123 = r123['accuracy_gap']
    ckpt_rows.append({
        'epoch'                : ep,
        'noaug_s42_test'       : r42['test_acc_noaug'],
        'aug_s42_test'         : r42['test_acc_aug'],
        'gap_s42'              : round(gap42, 4),
        'noaug_s123_test'      : r123['test_acc_noaug'],
        'aug_s123_test'        : r123['test_acc_aug'],
        'gap_s123'             : round(gap123, 4),
        'mean_gap'             : round((gap42 + gap123) / 2, 4),
        'noaug_s42_trainloss'  : r42['train_loss_noaug'],
        'aug_s42_trainloss'    : r42['train_loss_aug'],
        'noaug_s123_trainloss' : r123['train_loss_noaug'],
        'aug_s123_trainloss'   : r123['train_loss_aug'],
    })
ckpt_df = pd.DataFrame(ckpt_rows)

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs('analysis', exist_ok=True)
gap_traj.to_csv('analysis/gap_trajectory.csv', index=False, float_format='%.4f')
ckpt_df .to_csv('analysis/checkpoint_stats.csv', index=False, float_format='%.6f')

# ── Acceptance checks ─────────────────────────────────────────────────────────
assert gap_traj.shape == (30, 4)
assert list(gap_traj.columns) == ['epoch','gap_seed42','gap_seed123','mean_gap']
assert gap_traj.isna().sum().sum() == 0
assert ckpt_df.shape[0] == 4
assert list(ckpt_df['epoch']) == [5, 10, 20, 30]
assert ckpt_df.isna().sum().sum() == 0
# Cross-consistency
for _, crow in ckpt_df.iterrows():
    ep = int(crow['epoch'])
    traj_gap42 = gap_traj.loc[gap_traj['epoch']==ep,'gap_seed42'].values[0]
    assert abs(traj_gap42 - crow['gap_s42']) < 1e-8
    assert abs(crow['gap_s42'] - round(crow['aug_s42_test']-crow['noaug_s42_test'], 4)) < 1e-8

print("All checks passed. Outputs written to analysis/.")
