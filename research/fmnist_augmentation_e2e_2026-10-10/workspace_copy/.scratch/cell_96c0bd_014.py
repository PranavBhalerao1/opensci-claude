
# Final verification checks
import os
from PIL import Image

png = 'figures/fig3_loss_curves.png'
pdf = 'figures/fig3_loss_curves.pdf'

png_size = os.path.getsize(png)
pdf_size = os.path.getsize(pdf)
img = Image.open(png)

print("=== Acceptance Checks ===")
print(f"[{'PASS' if os.path.exists(png) else 'FAIL'}] figures/fig3_loss_curves.png exists")
print(f"[{'PASS' if png_size > 30*1024 else 'FAIL'}] PNG > 30 KB: {png_size/1024:.1f} KB")
print(f"[{'PASS' if os.path.exists(pdf) else 'FAIL'}] figures/fig3_loss_curves.pdf exists: {pdf_size/1024:.1f} KB")
print(f"\nPNG dimensions: {img.size[0]}×{img.size[1]} px")
print(f"DPI: {img.info.get('dpi', 'n/a')}")

# Check subplots: load and check content
import matplotlib.image as mpimg
import numpy as np
arr = mpimg.imread(png)
print(f"\nImage array shape: {arr.shape}  dtype={arr.dtype}")
print(f"Pixel value range: [{arr.min():.3f}, {arr.max():.3f}]")

# Ensure not all blank
assert arr.std() > 0.01, "Image appears blank!"
print("[PASS] Image is not blank (std > 0.01)")
