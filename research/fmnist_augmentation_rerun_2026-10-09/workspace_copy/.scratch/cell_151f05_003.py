
import numpy as np
import pandas as pd
import json
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

# ── 1. Load data ──────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/delta_by_size.csv')
sizes = df['size'].values.astype(float)
delta = df['delta_mean'].values.astype(float)

# ── 2. OLS fit ────────────────────────────────────────────────────────────────
X = np.log2(sizes)
Y = delta
n = len(X)

slope, intercept, r_value, p_value, se = stats.linregress(X, Y)
a  = intercept
b  = slope
r2 = r_value**2
t_crit        = stats.t.ppf(0.975, df=n-2)
slope_ci_low  = b - t_crit * se
slope_ci_high = b + t_crit * se

print(f"a={a:.6f}, b={b:.6f}, R²={r2:.6f}, p={p_value:.6f}")
print(f"slope 95% CI=[{slope_ci_low:.6f}, {slope_ci_high:.6f}]")

# ── 3. N* and interpretive note ───────────────────────────────────────────────
SIZE_MIN, SIZE_MAX = sizes.min(), sizes.max()

if b >= 0:
    N_star = 2.0 ** (-a / b)
    if N_star < SIZE_MIN:
        N_star_note = 'extrapolated_below_range'
    elif N_star > SIZE_MAX:
        N_star_note = 'extrapolated_above_range'
    else:
        N_star_note = 'within_tested_range'
else:
    N_star = float('nan')
    N_star_note = 'no_crossover_negative_slope'

if r2 < 0.5:
    N_star_note += '|R2_below_0.5'

print(f"\nN* = {N_star:.2f}  [{SIZE_MIN:.0f}–{SIZE_MAX:.0f}]")
print(f"note: {N_star_note}")

# ── 4. Bootstrap (5000 iterations) ───────────────────────────────────────────
rng  = np.random.default_rng(42)
BOOT = 5000
N_star_boot_list = []

for i in range(BOOT):
    idx = rng.integers(0, n, size=n)          # sample WITH replacement
    Xb, Yb = X[idx], Y[idx]
    # Need at least 2 distinct X values for linregress
    if len(np.unique(Xb)) < 2:
        # degenerate: assign nan → will clip to boundary
        N_star_boot_list.append(np.nan)
        continue
    sb, ab, *_ = stats.linregress(Xb, Yb)
    if sb == 0:
        N_star_b = 1e9
    else:
        N_star_b = 2.0 ** (-ab / sb)
    N_star_b = np.clip(N_star_b, 1.0, 1e9)
    N_star_boot_list.append(float(N_star_b))

N_star_boot_arr = np.array(N_star_boot_list)

# Replace NaN with median for CI (degenerate cases are rare)
nan_count = np.sum(np.isnan(N_star_boot_arr))
print(f"\nDegenerate bootstrap iterations (NaN): {nan_count}")
finite_vals = N_star_boot_arr[np.isfinite(N_star_boot_arr)]
N_star_ci_low  = float(np.percentile(finite_vals, 2.5))
N_star_ci_high = float(np.percentile(finite_vals, 97.5))
print(f"Bootstrap 95% CI for N*: [{N_star_ci_low:.2f}, {N_star_ci_high:.2f}]")
print(f"Bootstrap median N*: {np.median(finite_vals):.2f}")
