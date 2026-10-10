
import numpy as np
import pandas as pd
import json
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ── 1. Load data ──────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/delta_by_size.csv')
print("Input data:")
print(df[['size','delta_mean']].to_string(index=False))

sizes = df['size'].values.astype(float)
delta  = df['delta_mean'].values.astype(float)

# ── 2. Fit OLS: Δ = a + b·log₂(N) ───────────────────────────────────────────
X = np.log2(sizes)           # predictor
Y = delta                    # response

slope, intercept, r_value, p_value, se = stats.linregress(X, Y)
a = intercept
b = slope
r2 = r_value**2

# 95% CI for slope (t-distribution, df = n-2)
n = len(X)
t_crit = stats.t.ppf(0.975, df=n-2)
slope_ci_low  = b - t_crit * se
slope_ci_high = b + t_crit * se

print(f"\nOLS results:")
print(f"  intercept  a = {a:.6f}")
print(f"  slope      b = {b:.6f}")
print(f"  R²           = {r2:.6f}")
print(f"  p-value (b)  = {p_value:.6f}")
print(f"  95% CI slope = [{slope_ci_low:.6f}, {slope_ci_high:.6f}]")
