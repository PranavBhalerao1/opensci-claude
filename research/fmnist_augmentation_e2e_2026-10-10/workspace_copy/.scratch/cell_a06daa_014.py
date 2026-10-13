
import pandas as pd
import numpy as np

combined  = pd.read_csv("analysis/combined_metrics.csv")
gap_traj  = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats= pd.read_csv("analysis/checkpoint_stats.csv")

# Final consolidated numbers for the report
# ---- Epoch-5 values ----
ep5_row = gap_traj[gap_traj['epoch']==5].iloc[0]
gap_s42_ep5  = ep5_row['gap_seed42']    # -2.15
gap_s123_ep5 = ep5_row['gap_seed123']   # -3.25
mean_gap_ep5 = ep5_row['mean_gap']      # -2.700

# ---- Crossover scan ----
mean_gaps = gap_traj['mean_gap'].values
epochs    = gap_traj['epoch'].values
crossover_epoch = None
for i in range(len(epochs) - 2):
    ep = epochs[i]
    if ep > 28:
        break
    if mean_gaps[i] > 0 and mean_gaps[i+1] > 0 and mean_gaps[i+2] > 0:
        crossover_epoch = int(ep)
        break
crossover_statement = "No crossover within 30 epochs" if crossover_epoch is None else f"Crossover at epoch {crossover_epoch}"

# ---- Regime ----
if gap_s42_ep5 <= 0 and gap_s123_ep5 <= 0:
    regime = "underfitting-penalty-confirmed"
elif gap_s42_ep5 > 0 and gap_s123_ep5 > 0:
    regime = "early-benefit"
else:
    regime = "mixed"

# ---- Mean_gap at key epochs (from gap_trajectory.csv) ----
key_epochs = {5: None, 10: None, 20: None, 30: None}
for ep in key_epochs:
    key_epochs[ep] = gap_traj[gap_traj['epoch']==ep].iloc[0]['mean_gap']

# ---- Train/val stats at epochs 5 and 30 (from checkpoint_stats.csv, validated vs combined_metrics) ----
def get_stats(ep, seed, aug_flag):
    row = combined[(combined['seed']==seed) & (combined['augmented']==aug_flag) & (combined['epoch']==ep)].iloc[0]
    return {'train_loss': row['train_loss'], 'val_acc': row['val_acc'], 'test_acc': row['test_acc']}

stats = {}
for ep in [5, 30]:
    stats[ep] = {}
    for seed in [42, 123]:
        for aug_flag, lbl in [(False, 'noaug'), (True, 'aug')]:
            stats[ep][f'{lbl}_s{seed}'] = get_stats(ep, seed, aug_flag)

# ---- Divergence proxies ----
def delta_tl(ep):
    vals = []
    for seed in [42, 123]:
        aug_tl  = stats[ep][f'aug_s{seed}']['train_loss']
        noaug_tl= stats[ep][f'noaug_s{seed}']['train_loss']
        vals.append(aug_tl - noaug_tl)
    return vals[0], vals[1], np.mean(vals)

dtl_s42_ep5, dtl_s123_ep5, dtl_mean_ep5 = delta_tl(5)
dtl_s42_ep30, dtl_s123_ep30, dtl_mean_ep30 = delta_tl(30)

print("All key numbers compiled:")
print(f"  regime: {regime}")
print(f"  crossover: {crossover_statement}")
print(f"  gap_s42_ep5={gap_s42_ep5}, gap_s123_ep5={gap_s123_ep5}, mean_gap_ep5={mean_gap_ep5}")
print(f"  mean_gap_ep10={key_epochs[10]}, mean_gap_ep20={key_epochs[20]}, mean_gap_ep30={key_epochs[30]}")
print(f"  Δtrain_loss ep5: s42={dtl_s42_ep5:.6f}, s123={dtl_s123_ep5:.6f}, mean={dtl_mean_ep5:.6f}")
print(f"  Δtrain_loss ep30: s42={dtl_s42_ep30:.6f}, s123={dtl_s123_ep30:.6f}, mean={dtl_mean_ep30:.6f}")
print(f"  Max mean_gap: {gap_traj['mean_gap'].max():.4f} at epoch {gap_traj.loc[gap_traj['mean_gap'].idxmax(),'epoch']}")
