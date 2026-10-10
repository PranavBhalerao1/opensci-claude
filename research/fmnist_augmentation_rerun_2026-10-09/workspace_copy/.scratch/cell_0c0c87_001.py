
import pandas as pd

# ── Check results_seed123.csv ──────────────────────────────────────────────
df = pd.read_csv("results/results_seed123.csv")

print(f"Row count : {len(df)}  (expected 70)")
print(f"Columns   : {df.columns.tolist()}")
print(f"Seeds     : {sorted(df['seed'].unique().tolist())}")
print(f"Sizes     : {sorted(df['size'].unique().tolist())}")
print(f"Conditions: {sorted(df['condition'].unique().tolist())}")
print(f"Epochs    : {sorted(df['epoch'].unique().tolist())}")
print(f"NaN in train_loss : {df['train_loss'].isna().sum()}")
print(f"NaN in val_acc    : {df['val_acc'].isna().sum()}")
print(f"NaN in test_acc   : {df['test_acc'].isna().sum()}  (expected 56 – only epoch-5 populated)")

print("\n── Head ──")
print(df.head(5).to_string())
print("\n── Tail ──")
print(df.tail(5).to_string())

# ── Check gpu_log_seed123.txt ──────────────────────────────────────────────
with open("results/gpu_log_seed123.txt") as f:
    log = f.read()
print("\n── GPU Log ──")
print(log)

# ── Acceptance checklist ──────────────────────────────────────────────────
expected_sizes = [500, 1000, 2500, 5000, 10000, 30000, 60000]
checks = {
    "70 rows"          : len(df) == 70,
    "all 7 sizes"      : sorted(df['size'].unique().tolist()) == expected_sizes,
    "both conditions"  : set(df['condition'].unique()) == {'noaug', 'aug'},
    "no NaN train_loss": df['train_loss'].isna().sum() == 0,
    "no NaN val_acc"   : df['val_acc'].isna().sum() == 0,
    "device in log"    : "NVIDIA" in log or "CUDA" in log,
}
for name, result in checks.items():
    status = "✓ PASS" if result else "✗ FAIL"
    print(f"  {status}  {name}")
