import numpy as np, os

# ── Verify npz ────────────────────────────────────────────────────────────────
npz = np.load("data/subset_indices.npz")
keys = sorted(npz.files)
print(f"Keys in npz : {len(keys)}  ✓" if len(keys)==28 else f"FAIL: {len(keys)} keys")

# Spot-check acceptance criteria
# 1) N=500, seed=42 train: all 10 per-class counts in [44,46]
import torchvision, torchvision.transforms as transforms
ds = torchvision.datasets.FashionMNIST(root="data/", train=True, download=False,
                                        transform=transforms.ToTensor())
y = np.array(ds.targets)
tr500 = npz["train_500_42"]
counts = np.bincount(y[tr500], minlength=10)
print(f"N=500 seed=42 per-class counts: {counts.tolist()}")
assert all(44 <= c <= 46 for c in counts), "FAIL: out of [44,46]"
print("  ✓ all in [44,46]")

# 2) N=1000 seed=42 training size ≈ 900
tr1000 = npz["train_1000_42"]
print(f"N=1000 seed=42 train size: {len(tr1000)}  (expected 900)")
assert len(tr1000) == 900

# ── Verify class_balance_check.txt ───────────────────────────────────────────
txt_path = "data/class_balance_check.txt"
assert os.path.exists(txt_path)
size = os.path.getsize(txt_path)
print(f"\nclass_balance_check.txt: {size} bytes  ✓")
with open(txt_path) as f:
    print(f.read())
