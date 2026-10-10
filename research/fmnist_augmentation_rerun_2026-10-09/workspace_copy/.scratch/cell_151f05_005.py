
import numpy as np
import pandas as pd
import json
import os
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

os.makedirs('analysis', exist_ok=True)

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

# ── 3. N* and interpretive note ───────────────────────────────────────────────
SIZE_MIN, SIZE_MAX = sizes.min(), sizes.max()

if b >= 0:
    N_star = float(2.0 ** (-a / b))
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

print(f"a={a:.6f}, b={b:.6f}, R²={r2:.6f}, p={p_value:.6f}")
print(f"slope 95% CI=[{slope_ci_low:.6f}, {slope_ci_high:.6f}]")
print(f"N* = {N_star:.2f}, note: {N_star_note}")

# ── 4. Bootstrap (5000 iterations) ───────────────────────────────────────────
rng  = np.random.default_rng(42)
BOOT = 5000
N_star_boot_list = []

for i in range(BOOT):
    idx = rng.integers(0, n, size=n)
    Xb, Yb = X[idx], Y[idx]
    if len(np.unique(Xb)) < 2:
        N_star_boot_list.append(float('nan'))
        continue
    sb, ab, *_ = stats.linregress(Xb, Yb)
    if sb == 0:
        N_star_b = 1e9
    else:
        N_star_b = 2.0 ** (-ab / sb)
    N_star_b = float(np.clip(N_star_b, 1.0, 1e9))
    N_star_boot_list.append(N_star_b)

N_star_boot_arr = np.array(N_star_boot_list)
nan_count = int(np.sum(np.isnan(N_star_boot_arr)))
finite_vals = N_star_boot_arr[np.isfinite(N_star_boot_arr)]

N_star_ci_low  = float(np.percentile(finite_vals, 2.5))
N_star_ci_high = float(np.percentile(finite_vals, 97.5))

print(f"\nDegenerate bootstrap its: {nan_count}")
print(f"Bootstrap 95% CI: [{N_star_ci_low:.2f}, {N_star_ci_high:.2f}]")
print(f"Bootstrap median: {float(np.median(finite_vals)):.2f}")

# ── 5. Save bootstrap CSV ─────────────────────────────────────────────────────
boot_df = pd.DataFrame({
    'iter':        np.arange(1, BOOT+1, dtype=int),
    'N_star_boot': N_star_boot_arr
})
boot_df.to_csv('analysis/bootstrap_N_star.csv', index=False)
assert len(boot_df) == 5000
print(f"\n✓ bootstrap_N_star.csv saved — {boot_df.shape}")
print(boot_df['N_star_boot'].describe())

# ── 6. Save regression_results.json ──────────────────────────────────────────
results = {
    "a":             float(a),
    "b":             float(b),
    "r2":            float(r2),
    "slope_p_value": float(p_value),
    "slope_ci_low":  float(slope_ci_low),
    "slope_ci_high": float(slope_ci_high),
    "N_star":        float(N_star),
    "N_star_ci_low": float(N_star_ci_low),
    "N_star_ci_high":float(N_star_ci_high),
    "N_star_note":   N_star_note,
    # provenance
    "provenance": {
        "input_file":        "analysis/delta_by_size.csv",
        "method":            "OLS via scipy.stats.linregress; predictor=log2(size)",
        "bootstrap_seed":    42,
        "bootstrap_iters":   BOOT,
        "slope_ci_method":   "t-distribution, df=n-2",
        "N_star_ci_method":  "percentile bootstrap 2.5th/97.5th",
        "N_star_clip":       [1, 1e9],
        "analysis_date":     "2026-10-09",
        "analyst":           "Statistician agent"
    }
}

with open('analysis/regression_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n✓ regression_results.json saved")

# ── Validation ────────────────────────────────────────────────────────────────
with open('analysis/regression_results.json') as f:
    check = json.load(f)

required_keys = ['a','b','r2','N_star','N_star_ci_low','N_star_ci_high','N_star_note']
for k in required_keys:
    assert k in check, f"Missing key: {k}"
assert 0.0 <= check['r2'] <= 1.0, f"R² out of range: {check['r2']}"
print(f"✓ All required JSON keys present")
print(f"✓ R² = {check['r2']:.6f} (in [0,1])")
print(f"\nFinal JSON content:")
for k,v in check.items():
    if k != 'provenance':
        print(f"  {k}: {v}")
