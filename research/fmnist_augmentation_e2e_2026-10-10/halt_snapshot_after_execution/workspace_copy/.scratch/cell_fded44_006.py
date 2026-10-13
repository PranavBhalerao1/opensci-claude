
import pathlib, re
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker
from matplotlib.lines import Line2D

# ── 1. Load data ──────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/gap_trajectory.csv')
df = df.sort_values('epoch').reset_index(drop=True)

# ── 2. Parse crossover epoch ──────────────────────────────────────────────────
report_text     = pathlib.Path('analysis/crossover_report.txt').read_text()
no_cross_match  = re.search(r'CROSSOVER EPOCH:\s*No crossover', report_text, re.IGNORECASE)
epoch_match     = re.search(r'CROSSOVER EPOCH:\s*(\d+)', report_text, re.IGNORECASE)
crossover_epoch = None if no_cross_match else (int(epoch_match.group(1)) if epoch_match else None)
print(f"Crossover epoch: {crossover_epoch}")

# ── 3. Key scalars ────────────────────────────────────────────────────────────
def get_val(col, ep):
    return df.loc[df['epoch'] == ep, col].values[0]

epochs   = df['epoch'].to_numpy()
gap42    = df['gap_seed42'].to_numpy()
gap123   = df['gap_seed123'].to_numpy()
mean_gap = df['mean_gap'].to_numpy()

ep5_42   = get_val('gap_seed42',  5)
ep5_123  = get_val('gap_seed123', 5)
ep5_mean = get_val('mean_gap',    5)
print(f"Epoch-5: seed42={ep5_42:+.2f}  seed123={ep5_123:+.2f}  mean={ep5_mean:+.2f}")

closest_idx = int(np.argmax(mean_gap))
closest_ep  = int(epochs[closest_idx])
closest_val = float(mean_gap[closest_idx])

pathlib.Path('figures').mkdir(exist_ok=True)

# ── 4. Colours ────────────────────────────────────────────────────────────────
C_SEED42  = '#1f77b4'
C_SEED123 = '#ff7f0e'
C_MEAN    = 'black'
C_ZERO    = '#888888'

# ── 5. Build figure ───────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

# Zero reference line  ← acceptance check requirement
ax.axhline(0, color=C_ZERO, linewidth=1.4, linestyle='--', zorder=1,
           label='Zero reference (gap = 0)')

# Underfitting zone shading (epoch 1–5)
ax.axvspan(1, 5, alpha=0.07, color='steelblue', zorder=0)

# Epoch-5 vertical dotted marker
ax.axvline(5, color='#555555', linewidth=1.0, linestyle=':', alpha=0.75, zorder=2)
ax.text(5.22, -6.0, 'Epoch 5', rotation=90, va='bottom', ha='left',
        fontsize=8, color='#555555', style='italic')

# Per-seed lines
l42,   = ax.plot(epochs, gap42,  color=C_SEED42,  linewidth=1.6, linestyle='-',  zorder=3)
l123,  = ax.plot(epochs, gap123, color=C_SEED123, linewidth=1.6, linestyle='--', zorder=3)

# Bold mean line
lmean, = ax.plot(epochs, mean_gap, color=C_MEAN,   linewidth=3.2, linestyle='-',  zorder=4)

# Epoch-5 filled markers
m42   = ax.scatter([5], [ep5_42],   color=C_SEED42,  s=75,  zorder=6, marker='o')
m123  = ax.scatter([5], [ep5_123],  color=C_SEED123, s=75,  zorder=6, marker='D')
mmean = ax.scatter([5], [ep5_mean], color=C_MEAN,    s=100, zorder=7, marker='*')

# Labels for epoch-5 markers
ax.annotate(f'{ep5_42:+.2f} pp',
            xy=(5, ep5_42), xytext=(7.6, ep5_42 + 0.45),
            fontsize=8, color=C_SEED42,
            arrowprops=dict(arrowstyle='->', color=C_SEED42, lw=0.8))
ax.annotate(f'{ep5_123:+.2f} pp',
            xy=(5, ep5_123), xytext=(7.6, ep5_123 - 0.55),
            fontsize=8, color=C_SEED123,
            arrowprops=dict(arrowstyle='->', color=C_SEED123, lw=0.8))
ax.annotate(f'Mean: {ep5_mean:+.2f} pp',
            xy=(5, ep5_mean), xytext=(9.0, ep5_mean + 0.95),
            fontsize=8.5, color='#222222', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='#444444', lw=0.9))

# Crossover annotation
if crossover_epoch is not None:
    ax.axvline(crossover_epoch, color='crimson', linewidth=1.8,
               linestyle='-.', zorder=5)
    ax.text(crossover_epoch + 0.35, -0.5,
            f'Crossover (epoch {crossover_epoch})',
            color='crimson', fontsize=9.5, va='center',
            rotation=90, fontweight='bold')
else:
    ax.annotate(
        f'No crossover within 30 epochs\n'
        f'(closest: ep {closest_ep},  mean = {closest_val:+.3f} pp)',
        xy=(closest_ep, closest_val),
        xytext=(18.5, 0.95),
        fontsize=8.5, color='#3d3d00',
        bbox=dict(boxstyle='round,pad=0.45', fc='#fffde7',
                  ec='darkgoldenrod', alpha=0.93, lw=1.1),
        arrowprops=dict(arrowstyle='->', color='darkgoldenrod', lw=1.0),
        zorder=8
    )

# Regime banner (top-left)
ax.text(0.015, 0.976,
        'Regime: underfitting-penalty-confirmed\n'
        'Both seeds: gap < 0 at epoch 5 (mean = −2.70 pp)',
        transform=ax.transAxes, fontsize=7.8,
        va='top', ha='left', style='italic',
        bbox=dict(boxstyle='round,pad=0.40', fc='#eef4fb',
                  ec='#1f77b4', alpha=0.91, lw=1.0))

# Legend
legend_elements = [
    Line2D([0],[0], color=C_ZERO,    lw=1.4, ls='--',
           label='Zero reference  (gap = 0)'),
    Line2D([0],[0], color=C_SEED42,  lw=1.6, ls='-',
           label='Seed 42  (solid blue)'),
    Line2D([0],[0], color=C_SEED123, lw=1.6, ls='--',
           label='Seed 123  (dashed orange)'),
    Line2D([0],[0], color=C_MEAN,    lw=3.2, ls='-',
           label='Mean gap  (bold black)'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=C_SEED42,  ms=8,
           label=f'Seed 42 @ ep5: {ep5_42:+.2f} pp'),
    Line2D([0],[0], marker='D', color='w', markerfacecolor=C_SEED123, ms=7,
           label=f'Seed 123 @ ep5: {ep5_123:+.2f} pp'),
    Line2D([0],[0], marker='*', color='w', markerfacecolor=C_MEAN,    ms=11,
           label=f'Mean @ ep5: {ep5_mean:+.2f} pp'),
    mpatches.Patch(fc='steelblue', alpha=0.15, label='Underfitting zone (ep 1–5)'),
]
ax.legend(handles=legend_elements, loc='lower right',
          fontsize=7.8, framealpha=0.90, ncol=2,
          edgecolor='#aaaaaa', columnspacing=1.0, handlelength=2.2)

# Axes
ax.set_xlabel('Training Epoch', fontsize=12, labelpad=7)
ax.set_ylabel('Accuracy Gap: Aug − No-Aug (pp)', fontsize=12, labelpad=7)
ax.set_title('Augmentation Benefit Trajectory\n'
             'Fashion-MNIST · Small CNN · 2 Seeds × 30 Epochs',
             fontsize=13, fontweight='bold', pad=11)
ax.set_xlim(1, 30)
ax.set_ylim(-6.5, 1.8)
ax.set_xticks(range(1, 31, 2))
ax.tick_params(axis='x', labelsize=8.5)
ax.tick_params(axis='y', labelsize=9)
ax.grid(axis='y', alpha=0.28, linewidth=0.6)
ax.grid(axis='x', alpha=0.12, linewidth=0.5)

plt.tight_layout(pad=0.85)

# ── 6. Save ───────────────────────────────────────────────────────────────────
png_path = 'figures/fig2_accuracy_gap.png'
pdf_path = 'figures/fig2_accuracy_gap.pdf'
fig.savefig(png_path, dpi=300, bbox_inches='tight')
fig.savefig(pdf_path, dpi=300, bbox_inches='tight', format='pdf')
plt.close(fig)

# ── 7. Verify ─────────────────────────────────────────────────────────────────
for p in [png_path, pdf_path]:
    sz = pathlib.Path(p).stat().st_size
    status = '✓ OK (>20 KB)' if sz > 20_000 else '✗ TOO SMALL'
    print(f"{p}  →  {sz/1024:.1f} KB  {status}")
