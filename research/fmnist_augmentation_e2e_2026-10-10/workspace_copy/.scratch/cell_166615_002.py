
import pandas as pd
import pathlib, os, math

csv_path = pathlib.Path("data/metrics_seed123_aug.csv")

# ── 1. Load with plain pd.read_csv (no comment= kwarg, per spec) ──────────────
df = pd.read_csv(csv_path)

# The first column carries the metadata header string; rename it 'epoch'
first_col = df.columns[0]
df = df.rename(columns={first_col: "epoch"})
df["epoch"] = df["epoch"].astype(int)

print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print("\nDtypes:\n", df.dtypes)
print("\nHead(3):\n", df.head(3))

# ── 2. Structural checks ──────────────────────────────────────────────────────
checks = {}

# Row count
checks["row_count"]     = (len(df) == 30,  len(df))

# Required columns (after epoch rename)
req_cols = ["train_loss", "train_acc", "val_acc", "test_acc"]
missing  = [c for c in req_cols if c not in df.columns]
checks["required_cols"] = (len(missing) == 0, missing)

# No NaN
nan_count = df[req_cols].isna().sum().sum() if not missing else -1
checks["no_nan"]        = (nan_count == 0, nan_count)

# test_acc range  50 < val < 99
acc_min = df["test_acc"].min()
acc_max = df["test_acc"].max()
checks["acc_range"]     = (50 < acc_min and acc_max < 99, (acc_min, acc_max))

# epoch-5 test_acc
ep5_acc = df.loc[df["epoch"] == 5, "test_acc"].values[0]
checks["ep5_test_acc"]  = ep5_acc

print("\n=== Check results ===")
for k, v in checks.items():
    print(f"  {k}: {v}")

# ── 3. Print rows at epochs 1, 5, 10, 20, 30 ──────────────────────────────────
target_epochs = [1, 5, 10, 20, 30]
print("\n=== Key epoch rows ===")
print(df[df["epoch"].isin(target_epochs)].to_string(index=False))

# ── 4. Overall PASS / FAIL ────────────────────────────────────────────────────
bool_checks = [v[0] for v in checks.values() if isinstance(v, tuple)]
overall = "PASS" if all(bool_checks) else "FAIL"
print(f"\nOverall: {overall}")
