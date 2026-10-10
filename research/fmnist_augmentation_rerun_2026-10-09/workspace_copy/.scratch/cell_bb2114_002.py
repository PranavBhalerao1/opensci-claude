
import pandas as pd
import numpy as np

# ── 1. Load and inspect the CSV ────────────────────────────────────────────
df = pd.read_csv('results/results_seed42.csv')

print(f"Shape: {df.shape}")
print(f"Row count: {len(df)}  (expected 70)")
print(f"\nColumns: {df.columns.tolist()}")
print(f"\nFirst 5 rows:")
print(df.head())
print(f"\nLast 5 rows:")
print(df.tail())

# ── 2. Acceptance checks ──────────────────────────────────────────────────
print("\n--- Acceptance Checks ---")

# Row count
assert len(df) == 70, f"Expected 70 rows, got {len(df)}"
print(f"✓ Row count == 70")

# All 7 sizes present
expected_sizes = [500, 1000, 2500, 5000, 10000, 30000, 60000]
actual_sizes = sorted(df['size'].unique().tolist())
assert actual_sizes == expected_sizes, f"Sizes mismatch: {actual_sizes}"
print(f"✓ All 7 sizes present: {actual_sizes}")

# Both conditions present
actual_conds = sorted(df['condition'].unique().tolist())
assert actual_conds == ['aug', 'noaug'], f"Conditions mismatch: {actual_conds}"
print(f"✓ Both conditions present: {actual_conds}")

# No NaN in train_loss or val_acc
assert df['train_loss'].notna().all(), "NaN found in train_loss"
assert df['val_acc'].notna().all(), "NaN found in val_acc"
print(f"✓ No NaN values in train_loss or val_acc")

# Seed column
assert (df['seed'] == 42).all(), "Not all rows have seed=42"
print(f"✓ All rows have seed=42")

# Epoch structure
assert set(df['epoch'].unique()) == {1, 2, 3, 4, 5}, "Unexpected epoch values"
print(f"✓ Epochs 1-5 present")

# test_acc at epoch 5 only
epoch5 = df[df['epoch'] == 5]
assert epoch5['test_acc'].notna().all(), "NaN in test_acc at epoch 5"
non_epoch5 = df[df['epoch'] != 5]
assert non_epoch5['test_acc'].isna().all(), "test_acc should be NaN for epochs 1-4"
print(f"✓ test_acc populated only at epoch 5")

# Rows per (size, condition)
counts = df.groupby(['size', 'condition']).size()
assert (counts == 5).all(), f"Not all (size,condition) combos have 5 rows:\n{counts}"
print(f"✓ Each of 14 (size×condition) combos has exactly 5 epoch rows")

print("\n--- Summary statistics ---")
print(df.groupby(['size', 'condition'])[['train_loss', 'val_acc']].agg(['mean', 'min', 'max']).round(4))
