
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

# ── checkpoint_stats ─────────────────────────────────────────────────────────
ckpt_epochs = [5, 10, 20, 30]
ckpt_rows = []
for ep in ckpt_epochs:
    row_merged = merged[merged['epoch'] == ep]
    r42  = row_merged[row_merged['seed'] == 42].iloc[0]
    r123 = row_merged[row_merged['seed'] == 123].iloc[0]
    gap42  = r42['accuracy_gap']
    gap123 = r123['accuracy_gap']
    mean_gap = (gap42 + gap123) / 2
    ckpt_rows.append({
        'epoch'                : ep,
        'noaug_s42_test'       : r42['test_acc_noaug'],
        'aug_s42_test'         : r42['test_acc_aug'],
        'gap_s42'              : round(gap42, 4),
        'noaug_s123_test'      : r123['test_acc_noaug'],
        'aug_s123_test'        : r123['test_acc_aug'],
        'gap_s123'             : round(gap123, 4),
        'mean_gap'             : round(mean_gap, 4),
        'noaug_s42_trainloss'  : r42['train_loss_noaug'],
        'aug_s42_trainloss'    : r42['train_loss_aug'],
        'noaug_s123_trainloss' : r123['train_loss_noaug'],
        'aug_s123_trainloss'   : r123['train_loss_aug'],
    })
ckpt_df = pd.DataFrame(ckpt_rows)

# ── Cross-validate gap_trajectory vs checkpoint_stats ─────────────────────────
print("=== Acceptance checks ===")
# 1) gap_trajectory shape
assert gap_traj.shape == (30, 4), f"Bad shape: {gap_traj.shape}"
print("✓ gap_trajectory has 30 rows and 4 columns")

# 2) gap_trajectory columns
assert list(gap_traj.columns) == ['epoch','gap_seed42','gap_seed123','mean_gap']
print("✓ gap_trajectory columns correct")

# 3) No NaN
assert gap_traj.isna().sum().sum() == 0
print("✓ gap_trajectory no NaN")

# 4) checkpoint_stats rows
assert ckpt_df.shape[0] == 4
assert list(ckpt_df['epoch']) == [5,10,20,30]
print("✓ checkpoint_stats has 4 rows for epochs 5,10,20,30")

# 5) No NaN in ckpt
assert ckpt_df.isna().sum().sum() == 0
print("✓ checkpoint_stats no NaN")

# 6) Cross-check: gap_seed42 at checkpoint epochs must match aug_s42_test - noaug_s42_test
for _, crow in ckpt_df.iterrows():
    ep = int(crow['epoch'])
    traj_gap42 = gap_traj.loc[gap_traj['epoch']==ep,'gap_seed42'].values[0]
    ckpt_gap42 = crow['gap_s42']
    computed   = round(crow['aug_s42_test'] - crow['noaug_s42_test'], 4)
    assert abs(traj_gap42 - ckpt_gap42) < 1e-8, \
        f"Epoch {ep}: traj gap42={traj_gap42} != ckpt gap42={ckpt_gap42}"
    assert abs(ckpt_gap42 - computed) < 1e-8, \
        f"Epoch {ep}: ckpt gap42={ckpt_gap42} != aug-noaug={computed}"
print("✓ gap_seed42 consistent between gap_trajectory and checkpoint_stats")

for _, crow in ckpt_df.iterrows():
    ep = int(crow['epoch'])
    traj_gap123 = gap_traj.loc[gap_traj['epoch']==ep,'gap_seed123'].values[0]
    ckpt_gap123 = crow['gap_s123']
    computed    = round(crow['aug_s123_test'] - crow['noaug_s123_test'], 4)
    assert abs(traj_gap123 - ckpt_gap123) < 1e-8
    assert abs(ckpt_gap123 - computed) < 1e-8
print("✓ gap_seed123 consistent between gap_trajectory and checkpoint_stats")

print("\nAll acceptance checks passed!")
