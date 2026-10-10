
import os, pandas as pd, numpy as np
from pathlib import Path

# ── 1. Required directories ───────────────────────────────────────────────────
required_dirs = [
    "src", "data", "data/checkpoints", "data/logs",
    "data/predictions", "analysis", "figures", "tables", "results", "scripts"
]
print("=== Directory check ===")
for d in required_dirs:
    ok = Path(d).is_dir()
    print(f"  {'✓' if ok else '✗'} {d}")

# ── 2. Source files ───────────────────────────────────────────────────────────
print("\n=== Source files ===")
for f in ["src/model.py", "src/train.py", "data/environment_report.txt"]:
    p = Path(f)
    size = p.stat().st_size if p.exists() else 0
    print(f"  {'✓' if p.exists() else '✗'} {f}  ({size} bytes)")

# ── 3. Smoke-test outputs ─────────────────────────────────────────────────────
print("\n=== Smoke-test outputs ===")
log_df = pd.read_csv("data/logs/smoke_test_log.csv")
print(f"  CSV log shape  : {log_df.shape}")
print(log_df.to_string(index=False))

npz = np.load("data/predictions/smoke_test_predictions.npz")
print(f"\n  Predictions npz keys : {list(npz.keys())}")
print(f"  predictions shape    : {npz['predictions'].shape}")
print(f"  true_labels shape    : {npz['true_labels'].shape}")
print(f"  probabilities shape  : {npz['probabilities'].shape}")
print(f"  Accuracy (manual)    : {(npz['predictions']==npz['true_labels']).mean():.4f}")

# ── 4. Environment report content check ──────────────────────────────────────
print("\n=== Environment report CUDA check ===")
report_text = Path("data/environment_report.txt").read_text()
has_cuda = "cuda" in report_text.lower()
print(f"  Contains 'cuda' (case-insensitive): {has_cuda}")
print(f"  Contains 'GPU device name'         : {'GPU device name' in report_text}")
print(f"  File size                          : {len(report_text)} chars")
