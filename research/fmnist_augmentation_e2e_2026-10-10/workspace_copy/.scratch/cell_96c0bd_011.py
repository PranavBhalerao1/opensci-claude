
# Display figure for visual inspection
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

img = mpimg.imread('figures/fig3_loss_curves.png')
print(f"Image array shape: {img.shape}")
fig, ax = plt.subplots(figsize=(12, 8))
ax.imshow(img)
ax.axis('off')
plt.tight_layout()
plt.savefig('figures/_preview_fig3.png', dpi=72, bbox_inches='tight')
plt.close()
print("Preview saved.")
