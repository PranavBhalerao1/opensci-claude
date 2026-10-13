import os, csv

# ── 1. CSV verification ──────────────────────────────────────────────────────
csv_path = "/tmp/smoke_out/metrics_seed42_noaug.csv"
assert os.path.isfile(csv_path), f"CSV not found: {csv_path}"

with open(csv_path) as f:
    raw = f.read()

print("=== CSV raw content ===")
print(raw)

# Count data rows (skip comment lines starting with #)
lines = [l for l in raw.splitlines() if l and not l.startswith("#")]
header = lines[0]
data_rows = lines[1:]
print(f"Header : {header}")
print(f"Data rows: {len(data_rows)}")
assert len(data_rows) == 5, f"Expected 5 rows, got {len(data_rows)}"
print("✓ CSV has exactly 5 data rows")

# ── 2. Checkpoint verification ───────────────────────────────────────────────
ckpt_dir = "/tmp/smoke_out/checkpoints"
ckpts = sorted(os.listdir(ckpt_dir))
print(f"\n=== Checkpoints in {ckpt_dir} ===")
for c in ckpts:
    full = os.path.join(ckpt_dir, c)
    print(f"  {c}  ({os.path.getsize(full):,} bytes)")
assert len(ckpts) >= 1, "No checkpoint files found"
print(f"✓ {len(ckpts)} checkpoint file(s) present")

# ── 3. Load and inspect the checkpoint ──────────────────────────────────────
import torch
ckpt_path = os.path.join(ckpt_dir, ckpts[0])
ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
print(f"\n=== Checkpoint keys ===")
for k, v in ckpt.items():
    if k not in ("model_state", "optim_state"):
        print(f"  {k}: {v}")
print(f"  model_state keys: {len(ckpt['model_state'])} tensors")
assert ckpt["epoch"] == 5
assert ckpt["seed"] == 42
assert ckpt["augment"] == False
print("✓ Checkpoint contents verified (epoch=5, seed=42, augment=False)")
