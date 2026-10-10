
import pandas as pd
import numpy as np
from scipy import stats

# Reload every run to avoid NameError
delta_df   = pd.read_csv('analysis/delta_by_size.csv')
results_df = pd.read_csv('analysis/results_all.csv')

sizes      = delta_df['size'].values
delta_mean = delta_df['delta_mean'].values
d42        = delta_df['delta_seed42'].values
d123       = delta_df['delta_seed123'].values

# ---- Spearman ----
rho, p_value = stats.spearmanr(sizes, delta_mean)
print(f"Spearman rho={rho:.6f}  p={p_value:.6f}")

# ---- Concordance ----
concordant_flags = np.sign(d42) == np.sign(d123)
n_concordant     = concordant_flags.sum()
concordance_frac = n_concordant / len(sizes)

print(f"\nConcordance: {n_concordant}/{len(sizes)}  frac={concordance_frac:.4f}")
for sz, a, b, c in zip(sizes, d42, d123, concordant_flags):
    print(f"  size={sz:>6}  Δ42={a:+.3f}  Δ123={b:+.3f}  {'✓' if c else '✗'}")

# ---- Epoch-1 loss comparison ----
ep1 = results_df[results_df['epoch'] == 1].copy()
print(f"\nEpoch-1 rows: {len(ep1)}")
print(ep1[['seed','size','condition','train_loss']].head(16))
