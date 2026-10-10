
import json, sys, importlib, pathlib, torch

# ── 1. config.json validity & required keys ──────────────────────────────────
cfg_path = pathlib.Path("config/config.json")
with open(cfg_path) as f:
    cfg = json.load(f)

required_keys = {"architecture", "training", "augmentation", "normalization", "sizes", "seeds"}
missing = required_keys - cfg.keys()
assert not missing, f"Missing config keys: {missing}"
print("✓ config/config.json is valid JSON with all required keys:", sorted(cfg.keys()))
print("  architecture :", cfg["architecture"])
print("  training     :", cfg["training"])
print("  augmentation :", cfg["augmentation"])
print("  normalization:", cfg["normalization"])
print("  sizes        :", cfg["sizes"])
print("  seeds        :", cfg["seeds"])

# ── 2. importability & exports ────────────────────────────────────────────────
sys.path.insert(0, "src")
import train_fmnist as tm

for name in ("SmallCNN", "get_transforms", "train_one_epoch", "evaluate_accuracy"):
    assert hasattr(tm, name), f"Missing export: {name}"
print("\n✓ src/train_fmnist.py is importable and exports all required symbols")

# ── 3. SmallCNN forward-pass test (4,1,28,28) → (4,10) ───────────────────────
model = tm.SmallCNN()
model.eval()
x = torch.zeros(4, 1, 28, 28)
with torch.no_grad():
    out = model(x)

assert out.shape == (4, 10), f"Expected (4,10), got {out.shape}"
print(f"\n✓ SmallCNN forward pass: input {tuple(x.shape)} → output {tuple(out.shape)}")
print("  Output (raw logits):\n", out)

# ── 4. Parameter / architecture sanity ───────────────────────────────────────
n_params = sum(p.numel() for p in model.parameters())
print(f"\n  Total parameters: {n_params:,}")
print("\n  Model summary:")
print(model)

# ── 5. Transform factory ──────────────────────────────────────────────────────
for cond in ("noaug", "aug"):
    tf = tm.get_transforms(cond)
    print(f"\n✓ get_transforms('{cond}'):\n  {tf}")

print("\n══ ALL ACCEPTANCE CHECKS PASSED ══")
