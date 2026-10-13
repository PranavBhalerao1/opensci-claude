
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np
import os, pathlib

# ── ensure output directory exists ──────────────────────────────────────────
pathlib.Path('figures').mkdir(exist_ok=True)

# ── load data ────────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/gap_trajectory.csv')
epochs    = df['epoch'].values
gap_s42   = df['gap_seed42'].values
gap_s123  = df['gap_seed123'].values
mean_gap  = df['mean_gap'].values

epoch5_idx = int(df.index[df['epoch'] == 5][0])
ep5_s42    = float(gap_s42[epoch5_idx])
ep5_s123   = float(gap_s123[epoch5_idx])
ep5_mean   = float(mean_gap[epoch5_idx])

crossover_epoch = None   # confirmed: no crossover within 30 epochs

print(f"epoch5 idx={epoch5_idx}, ep5_s42={ep5_s42}, ep5_s123={ep5_s123}")

# ── color / style constants ──────────────────────────────────────────────────
COLOR_S42   = '#1f77b4'    # blue  – seed 42  (solid)
COLOR_S123  = '#ff7f0e'    # orange – seed 123 (dashed)
COLOR_MEAN  = 'black'
COLOR_ZERO  = '#888888'

# ── figure ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

# ── ZERO REFERENCE LINE  (the acceptance-critical element) ──────────────────
zline = ax.axhline(y=0, color=COLOR_ZERO, linestyle='--', linewidth=1.4,
                   label='Zero reference (gap = 0)', zorder=1)
print(f"axhline(y=0) artist: {zline}")

# Verify the line is truly at y=0
print(f"Zero-line ydata: {zline.get_ydata()}")

# ── per-seed gap lines ───────────────────────────────────────────────────────
ax.plot(epochs, gap_s42, color=COLOR_S42, linestyle='-', linewidth=1.5,
        alpha=0.85, label='Gap seed 42 (solid, blue)')
ax.plot(epochs, gap_s123, color=COLOR_S123, linestyle='--', linewidth=1.5,
        alpha=0.85, label='Gap seed 123 (dashed, orange)')

# ── bold mean line ───────────────────────────────────────────────────────────
ax.plot(epochs, mean_gap, color=COLOR_MEAN, linestyle='-', linewidth=2.8,
        label='Mean gap (bold)', zorder=3)

# ── epoch-5 vertical marker + dots ──────────────────────────────────────────
ax.axvline(x=5, color='dimgray', linestyle=':', linewidth=1.2,
           alpha=0.6, zorder=2)
ax.plot(5, ep5_s42,  color=COLOR_S42,  marker='o', markersize=9,
        zorder=5, linestyle='None',
        label=f'Epoch-5 seed42 ({ep5_s42:+.2f} pp)')
ax.plot(5, ep5_s123, color=COLOR_S123, marker='o', markersize=9,
        zorder=5, linestyle='None',
        label=f'Epoch-5 seed123 ({ep5_s123:+.2f} pp)')

# text label for epoch-5 vertical marker
ax.text(5.25, -5.25, 'Epoch 5', fontsize=8.5, color='dimgray', va='bottom')

# ── crossover annotation ─────────────────────────────────────────────────────
ax.text(0.97, 0.97, 'No crossover within 30 epochs',
        transform=ax.transAxes, fontsize=9.5,
        color='crimson', va='top', ha='right',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff0f0',
                  edgecolor='crimson', alpha=0.85))

# ── axes labels / title / legend ─────────────────────────────────────────────
ax.set_xlabel('Training Epoch', fontsize=12)
ax.set_ylabel('Accuracy Gap: Aug − No-Aug (pp)', fontsize=12)
ax.set_title('Augmentation Benefit Trajectory\n'
             'Small CNN · Fashion-MNIST · 2 Seeds × 30 Epochs',
             fontsize=13, fontweight='bold')
ax.set_xlim(0.5, 30.5)
ax.set_ylim(-6.2, 1.5)
ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
ax.yaxis.set_major_locator(ticker.MultipleLocator(1))
ax.grid(True, which='major', alpha=0.25)
ax.grid(True, which='minor', alpha=0.10)

ax.legend(loc='lower right', fontsize=8.5, framealpha=0.9)

plt.tight_layout()

# ── verify y=0 is within visible axis range ───────────────────────────────
ymin, ymax = ax.get_ylim()
print(f"Y-axis range: [{ymin}, {ymax}]  — zero visible: {ymin < 0 < ymax}")

# ── save PNG ─────────────────────────────────────────────────────────────────
png_path = 'figures/fig2_accuracy_gap.png'
fig.savefig(png_path, dpi=300, bbox_inches='tight')
png_size = os.path.getsize(png_path)
print(f"\nPNG: {png_path}  size={png_size:,} bytes  (>20KB: {png_size > 20_000})")

# ── save PDF ─────────────────────────────────────────────────────────────────
pdf_path = 'figures/fig2_accuracy_gap.pdf'
fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
pdf_size = os.path.getsize(pdf_path)
print(f"PDF: {pdf_path}  size={pdf_size:,} bytes")

plt.close(fig)
print("\nAll done.")
