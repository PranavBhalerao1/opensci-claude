
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import json, os

os.makedirs('figures', exist_ok=True)

# ── Load ──────────────────────────────────────────────────────────────────────
df   = pd.read_csv('analysis/delta_by_size.csv')
with open('analysis/regression_results.json') as fh:
    reg = json.load(fh)
boot = pd.read_csv('analysis/bootstrap_N_star.csv')

a, b   = reg['a'], reg['b']
r2     = reg['r2']
p_val  = reg['slope_p_value']
N_star = reg['N_star']
N_lo   = reg['N_star_ci_low']
N_hi   = reg['N_star_ci_high']
note   = reg['N_star_note']

# ── Log₂ x-values ─────────────────────────────────────────────────────────────
df['log2_size'] = np.log2(df['size'])
x_obs  = df['log2_size'].values
y_obs  = df['delta_mean'].values
n      = len(x_obs)
y_hat  = a + b * x_obs
resid  = y_obs - y_hat
rmse   = np.sqrt(np.sum(resid**2) / (n - 2))
xbar   = x_obs.mean()
Sxx    = np.sum((x_obs - xbar)**2)

# ── Regression line & CI ──────────────────────────────────────────────────────
x_range = np.linspace(np.log2(500), np.log2(60000), 300)
y_pred  = a + b * x_range
se_fit  = rmse * np.sqrt(1/n + (x_range - xbar)**2 / Sxx)
y_lo    = y_pred - 1.96 * se_fit
y_hi    = y_pred + 1.96 * se_fit

# ── Figure setup ─────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5.5))

# --- CI shading ---
ax.fill_between(x_range, y_lo, y_hi, color='steelblue', alpha=0.18,
                label='OLS 95% CI band', zorder=1)

# --- Δ=0 reference line ---
ax.axhline(0, color='black', linewidth=1.2, linestyle='--', zorder=2,
           label='Δ = 0')

# --- OLS regression line ---
ax.plot(x_range, y_pred, color='steelblue', linewidth=2.0, zorder=3,
        label=f'OLS: Δ = {a:.2f} + {b:.3f}·log₂(N)\n  R²={r2:.3f}, p={p_val:.3f}')

# --- Seed scatter points ---
ax.scatter(df['log2_size'], df['delta_seed42'],
           marker='o', s=55, color='#999999', edgecolors='#555555',
           linewidths=0.6, zorder=5, label='Seed 42 (Δ per size)')
ax.scatter(df['log2_size'], df['delta_seed123'],
           marker='s', s=55, color='#bbbbbb', edgecolors='#555555',
           linewidths=0.6, zorder=5, label='Seed 123 (Δ per size)')

# --- Mean connected line ---
ax.plot(df['log2_size'], df['delta_mean'],
        color='black', linewidth=2.2, zorder=6,
        marker='D', markersize=7, markerfacecolor='black',
        label='Mean Δ')

# --- N* vertical line (extrapolated → skip vertical line, add annotation only) ---
is_extrapolated = 'extrapolated' in note.lower()
log2_Nstar = np.log2(N_star)

if not is_extrapolated:
    ax.axvline(log2_Nstar, color='crimson', linewidth=1.6,
               linestyle=':', zorder=4)

# Annotation box in plot margins
# Place annotation at right side, below Δ=0
ann_x = x_range[-1] - 0.15       # near right edge of data
ann_y_ols = a + b * x_range[-1]  # OLS value there

# Put annotation box inside the axes at a comfortable position
bbox_props = dict(boxstyle='round,pad=0.4', facecolor='lightyellow',
                  edgecolor='#aa8800', alpha=0.88)

# Format CI high – clipped at 1e9
ci_hi_str = f'{N_hi/1e6:.0f}M' if N_hi >= 1e6 else f'{N_hi:.0f}'
ci_lo_str = f'{N_lo/1e3:.0f}k'

ann_text = (
    f"N* = {N_star/1e6:.2f}M\n"
    f"95% CI: [{ci_lo_str}, {ci_hi_str}]\n"
    f"(extrapolated beyond\n tested range)"
)
ax.text(0.97, 0.97, ann_text,
        transform=ax.transAxes,
        fontsize=8.5, va='top', ha='right',
        bbox=bbox_props)

# ── Axes formatting ───────────────────────────────────────────────────────────
tick_sizes = [500, 1000, 2500, 5000, 10000, 30000, 60000]
tick_log2  = [np.log2(s) for s in tick_sizes]
tick_labels = ['500', '1k', '2.5k', '5k', '10k', '30k', '60k']

ax.set_xticks(tick_log2)
ax.set_xticklabels(tick_labels, fontsize=9)
ax.set_xlim(np.log2(400), np.log2(75000))

ax.set_xlabel('Training set size  N', fontsize=12)
ax.set_ylabel('Augmentation benefit  Δ  (pp)', fontsize=12)
ax.set_title('Augmentation Benefit Δ vs Training Set Size\n'
             'Fashion-MNIST · 5-epoch CNN · Horizontal flip + crop augmentation',
             fontsize=11, pad=10)

ax.grid(True, linestyle=':', linewidth=0.6, alpha=0.7)
ax.legend(loc='lower right', fontsize=8.5, framealpha=0.88)

# secondary top-axis label hint
ax.annotate('x-axis: log₂(N) scale', xy=(0.01, 0.02), xycoords='axes fraction',
            fontsize=7.5, color='#555555')

plt.tight_layout()
out_path = 'figures/fig_delta_vs_size.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"Saved: {out_path}  size={os.path.getsize(out_path)/1024:.1f} KB")
