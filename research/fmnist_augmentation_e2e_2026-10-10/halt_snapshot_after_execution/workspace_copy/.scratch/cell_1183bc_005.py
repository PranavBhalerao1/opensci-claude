
import pandas as pd, json, numpy as np, matplotlib, matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pathlib, os

matplotlib.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 11,
    'axes.linewidth': 1.2,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.direction': 'out',
    'ytick.direction': 'out',
    'figure.dpi': 150,
})

# ── Data ──────────────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/combined_metrics.csv')
with open('analysis/crossover_summary.json') as f:
    cx = json.load(f)

# Four subsets
s42_noaug = df[(df.seed==42)  & (df.augmented==False)].sort_values('epoch')
s42_aug   = df[(df.seed==42)  & (df.augmented==True )].sort_values('epoch')
s123_noaug= df[(df.seed==123) & (df.augmented==False)].sort_values('epoch')
s123_aug  = df[(df.seed==123) & (df.augmented==True )].sort_values('epoch')

# Colors / styles (spec: blue=no-aug, orange=aug; solid=42, dashed=123)
C_BLUE   = '#1f77b4'
C_ORANGE = '#ff7f0e'
LW = 1.9
ALPHA_MAIN = 0.92

# ── Figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8.5, 5.2))

# Plot four lines
lines = {}
lines['s42_noaug'] = ax.plot(s42_noaug.epoch,  s42_noaug.test_acc,
                              color=C_BLUE,   ls='-',  lw=LW, alpha=ALPHA_MAIN,
                              label='Seed 42 · No Aug', zorder=4)[0]
lines['s42_aug']   = ax.plot(s42_aug.epoch,    s42_aug.test_acc,
                              color=C_ORANGE, ls='-',  lw=LW, alpha=ALPHA_MAIN,
                              label='Seed 42 · Aug',    zorder=4)[0]
lines['s123_noaug']= ax.plot(s123_noaug.epoch, s123_noaug.test_acc,
                              color=C_BLUE,   ls='--', lw=LW, alpha=ALPHA_MAIN,
                              label='Seed 123 · No Aug', zorder=4)[0]
lines['s123_aug']  = ax.plot(s123_aug.epoch,   s123_aug.test_acc,
                              color=C_ORANGE, ls='--', lw=LW, alpha=ALPHA_MAIN,
                              label='Seed 123 · Aug',    zorder=4)[0]

# ── Epoch-5 vertical marker ───────────────────────────────────────────────────
ax.axvline(x=5, color='#555555', ls=':', lw=1.6, alpha=0.85, zorder=2,
           label='Epoch-5 target budget')

# Text annotation for epoch-5 line
y_annot = 83.8
ax.annotate('Epoch-5\ntarget budget',
            xy=(5, y_annot),
            xytext=(6.5, y_annot),
            fontsize=9, color='#444444',
            va='center',
            arrowprops=dict(arrowstyle='->', color='#555555', lw=1.1),
            zorder=6)

# ── Epoch-5 gap annotation box ────────────────────────────────────────────────
ep5_y_avg = (s42_noaug[s42_noaug.epoch==5].test_acc.values[0] +
             s123_noaug[s123_noaug.epoch==5].test_acc.values[0]) / 2
gap_text = (f"Epoch-5 gap:\n"
            f"  Seed 42:   {cx['gap_seed42_ep5']:+.2f} pp\n"
            f"  Seed 123: {cx['gap_seed123_ep5']:+.2f} pp\n"
            f"  Mean:       {cx['epoch5_mean_gap_pp']:+.2f} pp")

ax.text(0.97, 0.05, gap_text,
        transform=ax.transAxes,
        fontsize=8.5, family='monospace',
        ha='right', va='bottom',
        bbox=dict(boxstyle='round,pad=0.4', fc='#f8f8f8', ec='#cccccc', alpha=0.9))

# ── No-crossover annotation ───────────────────────────────────────────────────
cx_epoch = cx.get('crossover_epoch', None)
if cx_epoch is None:
    ax.text(0.98, 0.97,
            'No crossover within 30 epochs\n(underfitting-penalty confirmed)',
            transform=ax.transAxes, fontsize=8.5,
            ha='right', va='top',
            color='#333333',
            bbox=dict(boxstyle='round,pad=0.35', fc='#fff8e7',
                      ec='#e0c060', alpha=0.92))
else:
    ax.axvline(x=cx_epoch, color='red', ls='-.', lw=1.4, alpha=0.7,
               label=f'Crossover epoch {cx_epoch}')

# ── Marker dots at epoch 5 for all four runs ──────────────────────────────────
for subset, color, ls in [(s42_noaug, C_BLUE, 'o'),
                           (s42_aug,   C_ORANGE, 'o'),
                           (s123_noaug,C_BLUE, 's'),
                           (s123_aug,  C_ORANGE,'s')]:
    row = subset[subset.epoch==5]
    ax.scatter(row.epoch, row.test_acc, color=color,
               marker=ls, s=40, zorder=5, edgecolors='white', lw=0.6)

# ── Axes labels & title ───────────────────────────────────────────────────────
ax.set_xlabel('Training Epoch', fontsize=12, labelpad=6)
ax.set_ylabel('Test Accuracy (%)', fontsize=12, labelpad=6)
ax.set_title('Test Accuracy: Augmented vs Non-Augmented (Fashion-MNIST)',
             fontsize=13, fontweight='bold', pad=10)

ax.set_xlim(0.5, 30.5)
ax.set_ylim(80.5, 93.8)
ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
ax.yaxis.set_major_locator(ticker.MultipleLocator(2))
ax.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))
ax.tick_params(which='minor', length=2.5)

# ── Legend ─────────────────────────────────────────────────────────────────────
leg = ax.legend(loc='lower right', fontsize=9.5,
                framealpha=0.92, edgecolor='#cccccc',
                ncol=1, handlelength=2.4, handleheight=1.1,
                borderpad=0.7)

ax.grid(axis='y', lw=0.5, alpha=0.4, ls='--', color='grey')
ax.grid(axis='x', lw=0.4, alpha=0.25, ls='--', color='grey')

plt.tight_layout(pad=1.2)

# ── Save ──────────────────────────────────────────────────────────────────────
pathlib.Path('figures').mkdir(exist_ok=True)
png_path = 'figures/fig1_test_accuracy_curves.png'
pdf_path = 'figures/fig1_test_accuracy_curves.pdf'

fig.savefig(png_path, dpi=300, bbox_inches='tight')
fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
plt.close(fig)

# ── Verify ────────────────────────────────────────────────────────────────────
png_size = os.path.getsize(png_path)
pdf_size = os.path.getsize(pdf_path)
print(f"PNG saved: {png_path}  ({png_size/1024:.1f} KB)")
print(f"PDF saved: {pdf_path}  ({pdf_size/1024:.1f} KB)")
print(f"PNG > 20 KB: {png_size > 20_000}")
