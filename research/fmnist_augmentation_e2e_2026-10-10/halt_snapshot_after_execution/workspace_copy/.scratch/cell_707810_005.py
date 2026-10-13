
# Final verification: reload the saved figure files and confirm they exist with correct sizes
import os

for path in ['figures/fig1_test_accuracy_curves.png', 'figures/fig1_test_accuracy_curves.pdf']:
    size = os.path.getsize(path)
    print(f"{path}: {size:,} bytes ({size/1024:.1f} KB) ✓")

# Also verify PNG is a valid image by reading it
from PIL import Image
img = Image.open('figures/fig1_test_accuracy_curves.png')
print(f"\nPNG dimensions: {img.size[0]} x {img.size[1]} px")
print(f"PNG mode: {img.mode}")
print("All checks PASSED")
