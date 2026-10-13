
import os, pandas as pd, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

gap = pd.read_csv('analysis/gap_trajectory.csv')

# ── Style ─────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family"      : "DejaVu Sans",
    "font.size"        : 11,
    "axes.titlesize"   : 12,
    "axes.labelsize"   : 11,
    "xtick.labelsize"  : 10,
    "ytick.labelsize"  : 10,
    "axes.spines.top"  : False,
    "axes.spines.right": False,
    "figure.facecolor" : "white",
    "axes.facecolor"   : "#F9F9F9",
})

COLOR_S42  = "#2166AC"   # blue  — seed 42  (solid)
COLOR_S123 = "#D6604D"   # orange — seed 123 (dashed)
COLOR_MEAN = "#1A1A1A"   # near-black bold — mean gap
COLOR_ZERO = "#888888"   # grey zero reference
COLOR_EP5  = "#555555"   # epoch-5 vertical marker

fig, ax = plt.subplots(figsize=(9, 5.2))

ep = gap['epoch'].values

# Per-seed lines
ax.plot(ep, gap['gap_seed42'].values,  color=COLOR_S42,  lw=1.8, ls='-',
        label='Seed 42  (gap$_{aug-noaug}$)', zorder=3)
ax.plot(ep, gap['gap_seed123'].values, color=COLOR_S123, lw=1.8, ls='--',
        label='Seed 123 (gap$_{aug-noaug}$)', zorder=3)

# Mean gap bold line
ax.plot(ep, gap['mean_gap'].values,    color=COLOR_MEAN, lw=2.8, ls='-',
        label='Mean gap (across seeds)', zorder=4, alpha=0.85)

# Zero reference line
ax.axhline(0, color=COLOR_ZERO, lw=1.3, ls=':', zorder=1, alpha=0.9,
           label='Gap = 0  (crossover threshold)')

# Epoch-5 vertical marker
ax.axvline(5, color=COLOR_EP5, lw=1.5, ls='--', zorder=2, alpha=0.85)
ax.annotate('epoch 5\nmean gap\n−2.70 pp',
            xy=(5, -2.70), xytext=(6.8, -2.00),
            fontsize=9, color=COLOR_EP5, va='bottom',
            arrowprops=dict(arrowstyle='->', color=COLOR_EP5, lw=0.9))

# No-crossover annotation
ax.text(0.99, 0.97,
        'No crossover within 30 epochs\n(mean gap uniformly negative)',
        transform=ax.transAxes, ha='right', va='top',
        fontsize=9.5, color='#8B0000',
        bbox=dict(boxstyle='round,pad=0.35', fc='#FFF0F0', ec='#CC4444', lw=0.8))

# Shade "penalty zone"
ax.fill_between(ep, gap['mean_gap'].values, 0,
                where=gap['mean_gap'].values < 0,
                alpha=0.10, color=COLOR_S42, label='Penalty zone (mean gap < 0)')

ax.set_xlabel('Epoch', fontsize=11)
ax.set_ylabel('Accuracy gap: aug − no-aug  (pp)', fontsize=11)
ax.set_title(
    'Fig 2 — Accuracy Gap Trajectory: Augmentation vs. No-Augmentation\n'
    'Small CNN on Fashion-MNIST  ·  2 seeds × 30 epochs',
    fontsize=12, fontweight='bold', pad=10
)
ax.set_xlim(1, 30)
ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
ax.tick_params(axis='x', which='both', direction='in')
ax.grid(axis='y', color='#CCCCCC', lw=0.6, linestyle='-')
ax.legend(loc='lower right', fontsize=9, framealpha=0.9, edgecolor='#AAAAAA', ncol=1)

plt.tight_layout()

os.makedirs('figures', exist_ok=True)
for ext in ('png', 'pdf'):
    path = f'figures/fig2_accuracy_gap.{ext}'
    fig.savefig(path, dpi=300, bbox_inches='tight')
    sz = os.path.getsize(path) / 1024
    print(f"Saved {path}  ({sz:.1f} KB)")

plt.close(fig)
print("fig2 done.")
