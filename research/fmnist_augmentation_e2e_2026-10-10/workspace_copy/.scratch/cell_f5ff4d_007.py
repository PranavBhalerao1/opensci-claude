
# ── verification: reload the figure and inspect all lines ────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np
import os

# Check file existence and sizes
png_path = 'figures/fig2_accuracy_gap.png'
pdf_path = 'figures/fig2_accuracy_gap.pdf'

png_size = os.path.getsize(png_path)
pdf_size = os.path.getsize(pdf_path)
print(f"PNG size: {png_size:,} bytes  (>20KB: {png_size > 20_000})")
print(f"PDF size: {pdf_size:,} bytes  (>0 bytes: {pdf_size > 0})")

# Load the PNG and scan for a horizontal white/grey band at y=0
img = mpimg.imread(png_path)   # RGBA or RGB array
print(f"\nImage shape: {img.shape}")
h, w = img.shape[:2]
print(f"Image dimensions: {w}x{h} px")

# The plot y-range is [-6.2, 1.5]; y=0 is at fraction (1.5-0)/(1.5-(-6.2)) = 1.5/7.7 from top
# (after tight_layout margins, it won't be exact, but roughly in the upper third)
print(f"\nExpected y=0 position: roughly at {1.5/7.7*100:.1f}% from top of plot area")

# ── also re-create the figure in memory and inspect artists ─────────────────
import pandas as pd
import matplotlib.ticker as ticker

df = pd.read_csv('analysis/gap_trajectory.csv')
epochs   = df['epoch'].values
gap_s42  = df['gap_seed42'].values
gap_s123 = df['gap_seed123'].values
mean_gap = df['mean_gap'].values

fig2, ax2 = plt.subplots(figsize=(9, 5.5))
zline2 = ax2.axhline(y=0, color='#888888', linestyle='--', linewidth=1.4, label='Zero ref')
ax2.plot(epochs, gap_s42,  color='#1f77b4', linestyle='-',  linewidth=1.5)
ax2.plot(epochs, gap_s123, color='#ff7f0e', linestyle='--', linewidth=1.5)
ax2.plot(epochs, mean_gap, color='black',   linestyle='-',  linewidth=2.8)
ax2.set_xlim(0.5, 30.5)
ax2.set_ylim(-6.2, 1.5)

# List all Line2D artists
all_lines = ax2.get_lines()
print(f"\nAll Line2D artists in figure:")
for ln in all_lines:
    ydata = ln.get_ydata()
    print(f"  label='{ln.get_label()}', ydata[:3]={ydata[:3]}, is_axhline={len(set(ydata))==1 and ydata[0]==0}")

plt.close(fig2)

# ── confirm zero reference is at y=0 ────────────────────────────────────────
zero_lines = [ln for ln in all_lines
              if hasattr(ln.get_ydata(), '__len__')
              and len(set(np.round(ln.get_ydata(), 8))) == 1
              and float(list(set(np.round(ln.get_ydata(), 8)))[0]) == 0.0]
print(f"\nZero-reference horizontal lines found: {len(zero_lines)}")
for zl in zero_lines:
    print(f"  color={zl.get_color()}, linestyle={zl.get_linestyle()}, ydata={zl.get_ydata()}")
