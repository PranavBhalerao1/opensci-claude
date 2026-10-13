
import pandas as pd
import os, pathlib, torch

print("=" * 65)
print("STEP 1: Verify all four metric CSVs")
print("=" * 65)

csv_files = {
    "seed42_noaug":  "data/metrics_seed42_noaug.csv",
    "seed42_aug":    "data/metrics_seed42_aug.csv",
    "seed123_noaug": "data/metrics_seed123_noaug.csv",
    "seed123_aug":   "data/metrics_seed123_aug.csv",
}

summary_rows = []
all_ok = True

for label, path in csv_files.items():
    if not os.path.exists(path):
        print(f"  ✗ MISSING: {path}")
        all_ok = False
        continue

    # Read comment header
    with open(path) as f:
        header_line = f.readline().strip()

    # Read CSV (skipping comment line)
    df = pd.read_csv(path, comment="#")
    n_rows = len(df)
    has_nan = df.isnull().any().any()
    acc_min = df["test_acc"].min() * 100
    acc_max = df["test_acc"].max() * 100
    in_range = (50 <= acc_min) and (acc_max <= 99)

    # Extract epoch-5 and epoch-30 values
    ep5  = df[df["epoch"] == 5].iloc[0]
    ep30 = df[df["epoch"] == 30].iloc[0]

    # Device check
    device_not_cpu = "device=" in header_line and "device=cpu" not in header_line

    status = "✓" if (n_rows == 30 and not has_nan and in_range and device_not_cpu) else "✗"
    if status == "✗":
        all_ok = False

    print(f"\n  {status} {label}")
    print(f"     File    : {path}  ({os.path.getsize(path):,} bytes)")
    print(f"     Header  : {header_line}")
    print(f"     Rows    : {n_rows}  (need 30)")
    print(f"     NaN     : {has_nan}  (need False)")
    print(f"     test_acc range : [{acc_min:.1f}%, {acc_max:.1f}%]  (need [50,99])")
    print(f"     Device≠cpu: {device_not_cpu}")
    print(f"     Ep5  → train_loss={ep5['train_loss']:.4f} val_acc={ep5['val_acc']:.4f} test_acc={ep5['test_acc']:.4f}")
    print(f"     Ep30 → train_loss={ep30['train_loss']:.4f} val_acc={ep30['val_acc']:.4f} test_acc={ep30['test_acc']:.4f}")

    summary_rows.append({
        "condition": label,
        "ep5_test_acc":  round(ep5["test_acc"] * 100, 2),
        "ep30_test_acc": round(ep30["test_acc"] * 100, 2),
        "ep5_val_acc":   round(ep5["val_acc"] * 100, 2),
        "ep30_val_acc":  round(ep30["val_acc"] * 100, 2),
    })

print(f"\n{'='*65}")
print(f"CSV verification: {'ALL PASS' if all_ok else 'FAILURES DETECTED'}")
