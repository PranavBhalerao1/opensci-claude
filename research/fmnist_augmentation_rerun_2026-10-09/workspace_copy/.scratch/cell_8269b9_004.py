
# Verify: readable by PIL
from PIL import Image
img = Image.open('figures/fig_delta_vs_size.png')
print(f"Format={img.format}, size={img.size}, mode={img.mode}")
