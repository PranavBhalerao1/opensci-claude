
import numpy as np, os

# Check subset_indices.npz
npz = np.load('data/subset_indices.npz')
print("Keys in subset_indices.npz:", sorted(npz.files))
print("Total arrays:", len(npz.files))

# Show a few key names and shapes
for k in sorted(npz.files)[:8]:
    print(f"  {k}: {npz[k].shape}")
print("...")
for k in sorted(npz.files)[-4:]:
    print(f"  {k}: {npz[k].shape}")

# Check results/ and src/ dirs
os.makedirs('results', exist_ok=True)
print("\nFiles in src/:", os.listdir('src/'))
print("Files in data/:", [f for f in os.listdir('data/') if not os.path.isdir(f'data/{f}')])
