
# Final acceptance-check summary table
print("=" * 70)
print("ACCEPTANCE CHECK SUMMARY")
print("=" * 70)

import pandas as pd, os, torch

checks = {}

# 1. All four CSVs exist with exactly 30 rows
csv_files = {
    "seed42_noaug":  "data/metrics_seed42_noaug.csv",
    "seed42_aug":    "data/metrics_seed42_aug.csv",
    "seed123_noaug": "data/metrics_seed123_noaug.csv",
    "seed123_aug":   "data/metrics_seed123_aug.csv",
}
all_csvs_30rows = True
all_acc_in_range = True
all_no_nan = True
all_device_not_cpu = True

for label, path in csv_files.items():
    df = pd.read_csv(path, comment="#")
    with open(path) as f:
        hdr = f.readline()
    if len(df) != 30: all_csvs_30rows = False
    if df.isnull().any().any(): all_no_nan = False
    acc_pct = df["test_acc"] * 100
    if not ((acc_pct >= 50).all() and (acc_pct <= 99).all()): all_acc_in_range = False
    if "device=cpu" in hdr or "device=" not in hdr: all_device_not_cpu = False

print(f"[1] All 4 CSVs have exactly 30 data rows:         {'PASS ✓' if all_csvs_30rows else 'FAIL ✗'}")
print(f"[2] All test_acc values in [50%, 99%]:            {'PASS ✓' if all_acc_in_range else 'FAIL ✗'}")
print(f"[3] No NaN/missing values in any CSV:             {'PASS ✓' if all_no_nan else 'FAIL ✗'}")
print(f"[4] Each CSV header has CUDA device (not cpu):    {'PASS ✓' if all_device_not_cpu else 'FAIL ✗'}")

# 2. Checkpoint files for ep5 and ep30 (minimum 8)
ckpt_ep5_ep30 = True
for seed_str in ["seed42", "seed123"]:
    for aug_tag in ["noaug", "aug"]:
        for ep in [5, 30]:
            p = f"data/checkpoints/checkpoint_{seed_str}_{aug_tag}_ep{ep}.pt"
            if not os.path.exists(p):
                ckpt_ep5_ep30 = False
                print(f"   MISSING: {p}")

print(f"[5] Checkpoint files for ep5 & ep30 (8 min):     {'PASS ✓' if ckpt_ep5_ep30 else 'FAIL ✗'}")

# 3. All 16 checkpoints
all_16_ckpts = all(
    os.path.exists(f"data/checkpoints/checkpoint_{s}_{a}_ep{e}.pt")
    for s in ["seed42","seed123"]
    for a in ["noaug","aug"]
    for e in [5,10,20,30]
)
print(f"[6] All 16 checkpoint files present:              {'PASS ✓' if all_16_ckpts else 'FAIL ✗'}")

all_pass = all([all_csvs_30rows, all_acc_in_range, all_no_nan, all_device_not_cpu,
                ckpt_ep5_ep30, all_16_ckpts])
print()
print(f"{'='*70}")
print(f"OVERALL: {'ALL CHECKS PASSED ✓' if all_pass else 'SOME CHECKS FAILED ✗'}")
print(f"{'='*70}")
