
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

os.makedirs('figures', exist_ok=True)

df = pd.read_csv('analysis/combined_metrics.csv')

s42_noaug  = df[(df['seed']==42)  & (df['augmented']==False)].sort_values('epoch')
s42_aug    = df[(df['seed']==42)  & (df['augmented']==True)].sort_values('epoch')
s123_noaug = df[(df['seed']==123) & (df['augmented']==False)].sort_values('epoch')
s123_aug   = df[(df['seed']==123) & (df['augmented']==True)].sort_values('epoch')

# ── Figure setup ───────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

BLUE   = '#1f77b4'
ORANGE = '#ff7f0e'

# Plot four lines with exact color/style spec:
# blue=no-aug, orange=aug; solid=seed42, dashed=seed123
line1, = ax.plot(s42_noaug['epoch'],  s42_noaug['test_acc'],
                 color=BLUE,   linestyle='solid',  linewidth=2.0,
                 label='Seed 42 – No Aug')
line2, = ax.plot(s42_aug['epoch'],    s42_aug['test_acc'],
                 color=ORANGE, linestyle='solid',  linewidth=2.0,
                 label='Seed 42 – Augmented')
line3, = ax.plot(s123_noaug['epoch'], s123_noaug['test_acc'],
                 color=BLUE,   linestyle='dashed', linewidth=2.0,
                 label='Seed 123 – No Aug')
line4, = ax.plot(s123_aug['epoch'],   s123_aug['test_acc'],
                 color=ORANGE, linestyle='dashed', linewidth=2.0,
                 label='Seed 123 – Augmented')

# ── Epoch-5 vertical marker ────────────────────────────────────────────────────
ax.axvline(x=5, color='grey', linestyle='dashed', linewidth=1.4, alpha=0.85, zorder=2)
ax.text(5.3, ax.get_ylim()[0] + 0.5 if ax.get_ylim()[0] > 0 else 82.5,
        'Epoch-5\ntarget budget',
        color='grey', fontsize=9, va='bottom', ha='left',
        bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.7))

# ── "No crossover within 30 epochs" annotation ────────────────────────────────
ax.text(0.98, 0.05,
        'No crossover within 30 epochs\n(mean gap uniformly negative)',
        transform=ax.transAxes, fontsize=8, ha='right', va='bottom',
        color='#555555',
        bbox=dict(boxstyle='round,pad=0.3', fc='#f9f9f9', ec='#cccccc', alpha=0.85))

# ── Axis labels, title, legend ─────────────────────────────────────────────────
ax.set_xlabel('Training Epoch', fontsize=12)
ax.set_ylabel('Test Accuracy (%)', fontsize=12)
ax.set_title('Test Accuracy: Augmented vs Non-Augmented (Fashion-MNIST)',
             fontsize=13, fontweight='bold')
ax.set_xlim(1, 30)
ax.set_xticks([1, 5, 10, 15, 20, 25, 30])
ax.legend(loc='lower right', fontsize=10, framealpha=0.9)
ax.grid(True, linestyle=':', alpha=0.5)
ax.tick_params(labelsize=10)

plt.tight_layout()

# ── Save ───────────────────────────────────────────────────────────────────────
png_path = 'figures/fig1_test_accuracy_curves.png'
pdf_path = 'figures/fig1_test_accuracy_curves.pdf'
fig.savefig(png_path, dpi=300, bbox_inches='tight')
fig.savefig(pdf_path, dpi=300, bbox_inches='tight')

# ── Programmatic verification ──────────────────────────────────────────────────
lines = ax.get_lines()
# Count only data lines (not axvline)
data_lines = [l for l in lines if l.get_label() and not l.get_label().startswith('_')]
print(f"Total lines on axes: {len(lines)}")
print(f"Data lines (labeled): {len(data_lines)}")
for l in data_lines:
    xdata = l.get_xdata()
    ydata = l.get_ydata()
    print(f"  Label: {l.get_label()!r:35s} | color={l.get_color()} "
          f"| ls={l.get_linestyle()} | n_pts={len(xdata)}")

plt.close(fig)

# File-size check
import os
png_size = os.path.getsize(png_path)
pdf_size = os.path.getsize(pdf_path)
print(f"\nPNG size: {png_size:,} bytes ({png_size/1024:.1f} KB) — {'PASS' if png_size > 20*1024 else 'FAIL'}")
print(f"PDF size: {pdf_size:,} bytes ({pdf_size/1024:.1f} KB) — {'PASS' if pdf_size > 0 else 'FAIL'}")
