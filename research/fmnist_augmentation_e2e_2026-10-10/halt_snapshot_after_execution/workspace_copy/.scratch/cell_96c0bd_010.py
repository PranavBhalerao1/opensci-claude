
import os

png = 'figures/fig3_loss_curves.png'
pdf = 'figures/fig3_loss_curves.pdf'

png_size = os.path.getsize(png)
pdf_size = os.path.getsize(pdf)

print(f"PNG: {png_size:,} bytes  ({png_size/1024:.1f} KB)  — >30KB? {png_size > 30*1024}")
print(f"PDF: {pdf_size:,} bytes  ({pdf_size/1024:.1f} KB)")

# Quick PIL check on PNG dimensions
from PIL import Image
img = Image.open(png)
print(f"\nPNG dimensions: {img.size[0]}×{img.size[1]} px")
print(f"DPI info: {img.info.get('dpi', 'not embedded')}")
print(f"Mode: {img.mode}")
