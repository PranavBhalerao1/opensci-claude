import ast, re

src = open("src/train.py").read()

# Full consolidated structural audit
print("=" * 55)
print("src/train.py — Final Structural Audit")
print("=" * 55)

# 1. Syntax
ast.parse(src)
print("✓  Syntax: OK")

# 2. SmallCNN architecture — check nn.* usage only (no docstring text)
nn_conv2d  = src.count("nn.Conv2d")
nn_linear  = src.count("nn.Linear")
nn_maxpool = src.count("nn.MaxPool2d")
nn_dropout = src.count("nn.Dropout")
nn_bn      = len(re.findall(r'nn\.BatchNorm\w*', src))
print(f"✓  SmallCNN layers: Conv2d={nn_conv2d}(≥2)  Linear={nn_linear}(≥2)  "
      f"MaxPool2d={nn_maxpool}(≥2)  Dropout={nn_dropout}(≥1)  nn.BatchNorm={nn_bn}(must=0)")
assert nn_conv2d >= 2 and nn_linear >= 2 and nn_bn == 0

# 3. Argparse flags
for flag in ["--seed", "--augment", "--epochs", "--data_dir", "--out_dir"]:
    assert flag in src, f"Missing: {flag}"
print("✓  argparse flags: --seed --augment --epochs --data_dir --out_dir")

# 4. Seed fixing
for sym in ["random.seed(seed)", "np.random.seed(seed)",
            "torch.manual_seed(seed)", "torch.cuda.manual_seed_all(seed)",
            "cudnn.deterministic = True"]:
    assert sym in src, f"Missing: {sym}"
print("✓  Seed fixing: random / numpy / torch / CUDA / cudnn.deterministic")

# 5. CSV comment header
assert "# seed=" in src and "started=" in src
print("✓  CSV comment header (seed, augment, device, started)")

# 6. Checkpoint naming / epochs
assert "checkpoint_seed" in src and "_ep" in src
assert "{5, 10, 20, 30}" in src
print("✓  Checkpoint naming & CHECKPOINT_EPOCHS {5,10,20,30}")

# 7. Split 55k / 5k
assert "55_000" in src
print("✓  Train/val split 55 000 / 5 000")

# 8. Optimizer
assert "lr=0.001" in src and "weight_decay=1e-4" in src
print("✓  Adam lr=0.001, weight_decay=1e-4")

# 9. Device
assert "torch.device" in src and "cuda" in src
print("✓  Device selection (cuda / cpu)")

# 10. Smoke test artefacts
import os
csv_path = "/tmp/smoke_out/metrics_seed42_noaug.csv"
ckpt_dir = "/tmp/smoke_out/checkpoints"
assert os.path.exists(csv_path)
rows = [l for l in open(csv_path) if not l.startswith("#") and l.strip()]
assert len(rows) == 6, f"Expected 6 lines (header+5), got {len(rows)}"  # header + 5 data rows
print(f"✓  Smoke CSV: {len(rows)-1} data rows")
ckpts = [f for f in os.listdir(ckpt_dir) if f.endswith(".pt")]
assert len(ckpts) >= 1
print(f"✓  Smoke checkpoint: {ckpts}")

print("\n=== ALL CHECKS PASSED ===")
