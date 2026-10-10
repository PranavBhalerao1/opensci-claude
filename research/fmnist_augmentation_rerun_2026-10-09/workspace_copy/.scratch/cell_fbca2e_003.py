
import pandas as pd
import os

# ── Step 1: Concatenate ──────────────────────────────────────────────────────
df42  = pd.read_csv('results/results_seed42.csv')
df123 = pd.read_csv('results/results_seed123.csv')
df_all = pd.concat([df42, df123], ignore_index=True)

print(f"Concatenated shape: {df_all.shape}")
print(f"Total rows: {len(df_all)}")

# ── Step 2: Verify 140 rows and no missing combos ────────────────────────────
expected_sizes      = [500, 1000, 2000, 5000, 10000, 30000, 60000]
expected_conditions = ['noaug', 'aug']
expected_seeds      = [42, 123]
expected_epochs     = [1, 2, 3, 4, 5]

from itertools import product
expected_combos = set(product(expected_sizes, expected_conditions, expected_seeds, expected_epochs))
actual_combos   = set(zip(df_all['size'], df_all['condition'], df_all['seed'], df_all['epoch']))

missing = expected_combos - actual_combos
extra   = actual_combos   - expected_combos

if len(df_all) == 140:
    print("✓ Exactly 140 rows present")
else:
    print(f"✗ Row count mismatch: {len(df_all)} (expected 140)")

if missing:
    print(f"\n⚠ MISSING combos ({len(missing)}):")
    for m in sorted(missing):
        print(f"  size={m[0]}, condition={m[1]}, seed={m[2]}, epoch={m[3]}")
else:
    print("✓ No missing (size, condition, seed, epoch) combinations")

if extra:
    print(f"\n⚠ EXTRA combos ({len(extra)}):")
    for e in sorted(extra):
        print(f"  size={e[0]}, condition={e[1]}, seed={e[2]}, epoch={e[3]}")
else:
    print("✓ No extra combinations")
