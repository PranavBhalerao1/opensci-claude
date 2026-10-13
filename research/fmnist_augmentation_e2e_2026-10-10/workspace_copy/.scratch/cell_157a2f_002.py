
import pandas as pd
import pathlib, os

# ── paths ──────────────────────────────────────────────────────────────────────
csv_path   = pathlib.Path("data/metrics_seed123_noaug.csv")
check_dir  = pathlib.Path("data/run_checks")
check_dir.mkdir(parents=True, exist_ok=True)
out_path   = check_dir / "seed123_noaug_verified.txt"

# ── load ───────────────────────────────────────────────────────────────────────
df = pd.read_csv(csv_path)          # plain read_csv — matches verifier behaviour

print("=== Raw DataFrame ===")
print(f"Shape            : {df.shape}")
print(f"Columns          : {df.columns.tolist()}")
print()

# ── normalise column names ─────────────────────────────────────────────────────
# The first column embeds the metadata comment; rename it to 'epoch'
df.columns = ["epoch"] + [c.strip() for c in df.columns[1:]]
df["epoch"] = df["epoch"].astype(int)

print(f"Normalised cols  : {df.columns.tolist()}")
print(f"Dtype epoch      : {df['epoch'].dtype}")
print()

# ── checks ─────────────────────────────────────────────────────────────────────
REQUIRED_COLS = {"train_loss", "train_acc", "val_acc", "test_acc"}

check_rows    = (len(df) == 30)
check_cols    = REQUIRED_COLS.issubset(set(df.columns))
check_nan     = df.isnull().sum().sum() == 0
check_acc_lo  = df["test_acc"].min() >= 50.0
check_acc_hi  = df["test_acc"].max() <= 99.0

print(f"Exactly 30 rows  : {check_rows}  ({len(df)} rows)")
print(f"Required cols    : {check_cols}  (have: {set(df.columns)})")
print(f"No NaN           : {check_nan}  (total NaN={df.isnull().sum().sum()})")
print(f"test_acc ≥ 50    : {check_acc_lo}  (min={df['test_acc'].min():.2f}%)")
print(f"test_acc ≤ 99    : {check_acc_hi}  (max={df['test_acc'].max():.2f}%)")
print()

# ── spot-check rows ────────────────────────────────────────────────────────────
spot_epochs = [1, 5, 10, 20, 30]
spot = df[df["epoch"].isin(spot_epochs)].set_index("epoch")
print("=== Spot-check rows (epochs 1, 5, 10, 20, 30) ===")
print(spot[["train_loss", "train_acc", "val_acc", "test_acc"]].to_string())
print()

epoch5_test_acc = float(spot.loc[5, "test_acc"])
print(f"Epoch-5 test_acc : {epoch5_test_acc:.2f}%")

# ── overall verdict ────────────────────────────────────────────────────────────
all_pass = all([check_rows, check_cols, check_nan, check_acc_lo, check_acc_hi])
verdict  = "PASS" if all_pass else "FAIL"
print(f"\nOverall verdict  : {verdict}")
