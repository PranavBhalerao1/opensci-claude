
import pandas as pd
import numpy as np
from scipy import stats

# Reload
delta_df = pd.read_csv('analysis/delta_by_size.csv')
results_df = pd.read_csv('analysis/results_all.csv')

# ============================================================
# STEP 2: Spearman rank correlation — delta_mean vs size
# ============================================================
sizes = delta_df['size'].values
delta_mean = delta_df['delta_mean'].values

rho, p_value = stats.spearmanr(sizes, delta_mean)

print("=== SPEARMAN RANK CORRELATION ===")
print(f"sizes:       {sizes}")
print(f"delta_mean:  {delta_mean}")
print(f"Spearman rho = {rho:.6f}")
print(f"Two-tailed p = {p_value:.6f}")
