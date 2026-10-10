
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib.patches as mpatches
import json, os

os.makedirs('figures', exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/delta_by_size.csv')
with open('analysis/regression_results.json') as fh:
    reg = json.load(fh)
boot = pd.read_csv('analysis/bootstrap_N_star.csv')

# ── Regression parameters ─────────────────────────────────────────────────────
a        = reg['a']
b        = reg['b']
r2       = reg['r2']
p_val    = reg['slope_p_value']
N_star   = reg['N_star']
N_lo     = reg['N_star_ci_low']
N_hi     = reg['N_star_ci_high']
note     = reg['N_star_note']

# Compute OLS standard-error of prediction for CI band
# SE of regression line at each x: SE_fit = RMSE * sqrt(1/n + (x-xbar)²/Sxx)
x_obs  = np.log2(df['size'].values)
y_obs  = df['delta_mean'].values
n      = len(x_obs)
y_hat  = a + b * x_obs
resid  = y_obs - y_hat
rmse   = np.sqrt(np.sum(resid**2) / (n - 2))
xbar   = x_obs.mean()
Sxx    = np.sum((x_obs - xbar)**2)

# Regression line over extended range
x_range = np.linspace(np.log2(500), np.log2(60000), 200)
y_pred  = a + b * x_range
se_fit  = rmse * np.sqrt(1/n + (x_range - xbar)**2 / Sxx)
y_lo    = y_pred - 1.96 * se_fit
y_hi    = y_pred + 1.96 * se_fit

print(f"RMSE={rmse:.4f}, xbar={xbar:.3f}, Sxx={Sxx:.3f}")
print(f"SE range: [{se_fit.min():.4f}, {se_fit.max():.4f}]")
print(f"N* = {N_star:.0f}  [{N_lo:.0f}, {N_hi:.0f}]  note={note}")
print(df[['size','delta_seed42','delta_seed123','delta_mean']].to_string())
