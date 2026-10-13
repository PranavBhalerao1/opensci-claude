import os, csv, torch

# ---- CSV verification ----
csv_path = "/tmp/smoke_out/metrics_seed42_noaug.csv"
assert os.path.exists(csv_path), "CSV missing!"

with open(csv_path) as f:
    raw = f.read()

print("=== CSV contents ===")
print(raw)

# Parse skipping comment line
lines = [l for l in raw.strip().split("\n") if not l.startswith("#")]
reader = list(csv.reader(lines))
header = reader[0]
data   = reader[1:]
print(f"Header : {header}")
print(f"Data rows : {len(data)}  (expected 5)")
assert len(data) == 5, f"Expected 5 rows, got {len(data)}"
assert header[0] == "epoch"
print("CSV OK ✓")

# ---- Checkpoint verification ----
ckpt_dir = "/tmp/smoke_out/checkpoints"
ckpts = os.listdir(ckpt_dir)
print(f"\nCheckpoints found: {ckpts}")
assert len(ckpts) >= 1, "No checkpoint files!"

ckpt = torch.load(os.path.join(ckpt_dir, ckpts[0]), map_location="cpu", weights_only=False)
print(f"Checkpoint keys: {list(ckpt.keys())}")
print(f"Epoch in checkpoint: {ckpt['epoch']}")
print(f"val_acc: {ckpt['val_acc']:.4f}   test_acc: {ckpt['test_acc']:.4f}")
print("Checkpoint OK ✓")

# ---- Reload model and run forward pass ----
import sys; sys.path.insert(0, "src")
# Re-import SmallCNN fresh from the file
import importlib.util
spec_mod = importlib.util.spec_from_file_location("train", "src/train.py")
train_mod = importlib.util.module_from_spec(spec_mod)
spec_mod.loader.exec_module(train_mod)

model = train_mod.SmallCNN()
model.load_state_dict(ckpt["model_state"])
model.eval()
dummy = torch.zeros(4, 1, 28, 28)
with torch.no_grad():
    out = model(dummy)
print(f"\nReloaded model forward pass: {tuple(out.shape)}  ✓")
assert out.shape == (4, 10)
print("\nAll acceptance checks PASSED ✓")
