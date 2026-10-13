
import pandas as pd
import pathlib, os

# ── 1. Read CSV ──────────────────────────────────────────────────────────────
csv_path = "data/metrics_seed42_aug.csv"
df = pd.read_csv(csv_path)

# Rename the metadata-laden first column → "epoch" for clean checks
df = df.rename(columns={df.columns[0]: "epoch"})
df["epoch"] = df["epoch"].astype(int)

print("=== Columns after rename ===")
print(list(df.columns))
print(f"\nShape: {df.shape}  (expected 30 rows × 5 cols)")

# ── 2. CHECKS ────────────────────────────────────────────────────────────────
issues = []

# 2a. Row count
row_count = len(df)
row_ok = (row_count == 30)
print(f"\n[CHECK] Row count = {row_count}  → {'PASS' if row_ok else 'FAIL'}")
if not row_ok:
    issues.append(f"Row count {row_count} ≠ 30")

# 2b. Required columns present
required_cols = {"epoch", "train_loss", "val_acc", "test_acc"}
present_cols = set(df.columns)
cols_ok = required_cols.issubset(present_cols)
print(f"[CHECK] Required cols present = {required_cols.issubset(present_cols)}  → {'PASS' if cols_ok else 'FAIL'}")
missing = required_cols - present_cols
if missing:
    issues.append(f"Missing columns: {missing}")

# 2c. No NaN values
nan_count = df.isnull().sum().sum()
nan_ok = (nan_count == 0)
print(f"[CHECK] NaN count = {nan_count}  → {'PASS' if nan_ok else 'FAIL'}")
if not nan_ok:
    issues.append(f"NaN values found: {nan_count}")

# 2d. test_acc range [50, 99]
ta_min = df["test_acc"].min()
ta_max = df["test_acc"].max()
range_ok = (ta_min >= 50) and (ta_max <= 99)
print(f"[CHECK] test_acc range [{ta_min:.2f}, {ta_max:.2f}] ⊆ [50,99]  → {'PASS' if range_ok else 'FAIL'}")
if not range_ok:
    issues.append(f"test_acc out of [50,99]: min={ta_min:.2f}, max={ta_max:.2f}")

# ── 3. Sanity-check rows at epochs 1, 5, 10, 20, 30 ─────────────────────────
print("\n=== Sanity rows at epochs 1, 5, 10, 20, 30 ===")
sanity_epochs = [1, 5, 10, 20, 30]
sanity_df = df[df["epoch"].isin(sanity_epochs)].set_index("epoch")
print(sanity_df.to_string())

# Epoch-5 test_acc
ep5_test_acc = float(df.loc[df["epoch"] == 5, "test_acc"].values[0])
ep30_test_acc = float(df.loc[df["epoch"] == 30, "test_acc"].values[0])
print(f"\nEpoch-5  test_acc : {ep5_test_acc:.2f}%")
print(f"Epoch-30 test_acc : {ep30_test_acc:.2f}%")

# ── Overall status ───────────────────────────────────────────────────────────
status = "PASS" if (row_ok and cols_ok and nan_ok and range_ok) else "FAIL"
print(f"\n>>> Overall status: {status}")
if issues:
    for iss in issues:
        print(f"  ISSUE: {iss}")
