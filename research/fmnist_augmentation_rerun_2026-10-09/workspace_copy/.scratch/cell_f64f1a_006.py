
import pandas as pd
import numpy as np
from scipy import stats

delta_df   = pd.read_csv('analysis/delta_by_size.csv')
results_df = pd.read_csv('analysis/results_all.csv')

sizes      = delta_df['size'].values
delta_mean = delta_df['delta_mean'].values
d42        = delta_df['delta_seed42'].values
d123       = delta_df['delta_seed123'].values

# ---- Spearman ----
rho, p_value = stats.spearmanr(sizes, delta_mean)

# ---- Concordance ----
concordant_flags = np.sign(d42) == np.sign(d123)
n_concordant     = int(concordant_flags.sum())
concordance_frac = n_concordant / len(sizes)

# ---- Epoch-1 loss: aug > noaug? ----
ep1   = results_df[results_df['epoch'] == 1].copy()

# Pivot to wide per (seed, size)
ep1_aug   = ep1[ep1['condition'] == 'aug'  ][['seed','size','train_loss']].rename(columns={'train_loss':'loss_aug'})
ep1_noaug = ep1[ep1['condition'] == 'noaug'][['seed','size','train_loss']].rename(columns={'train_loss':'loss_noaug'})
ep1_wide  = ep1_aug.merge(ep1_noaug, on=['seed','size'])
ep1_wide['aug_gt_noaug'] = ep1_wide['loss_aug'] > ep1_wide['loss_noaug']

print("Epoch-1 loss comparison (wide):")
print(ep1_wide.to_string(index=False))

n_aug_higher  = int(ep1_wide['aug_gt_noaug'].sum())
total_comps   = len(ep1_wide)          # should be 14  (7 sizes × 2 seeds)
frac_aug_higher = n_aug_higher / total_comps

print(f"\nn_aug_higher  = {n_aug_higher}")
print(f"total_comps   = {total_comps}")
print(f"frac_aug_higher = {frac_aug_higher:.4f}  ({frac_aug_higher*100:.1f}%)")
