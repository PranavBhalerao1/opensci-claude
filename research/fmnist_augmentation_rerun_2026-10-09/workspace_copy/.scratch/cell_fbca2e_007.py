
import pandas as pd
import os
from itertools import product

# ── Load and concatenate ─────────────────────────────────────────────────────
df42  = pd.read_csv('results/results_seed42.csv')
df123 = pd.read_csv('results/results_seed123.csv')
df_all = pd.concat([df42, df123], ignore_index=True)

# ── Determine actual grid ────────────────────────────────────────────────────
actual_sizes      = sorted(df_all['size'].unique())
actual_conditions = sorted(df_all['condition'].unique())
actual_seeds      = sorted(df_all['seed'].unique())
actual_epochs     = sorted(df_all['epoch'].unique())

print(f"Sizes: {actual_sizes}")
print(f"Total rows: {len(df_all)}")

# ── Completeness check ───────────────────────────────────────────────────────
expected_combos = set(product(actual_sizes, actual_conditions, actual_seeds, actual_epochs))
actual_combos   = set(zip(df_all['size'], df_all['condition'], df_all['seed'], df_all['epoch']))
missing = expected_combos - actual_combos

print(f"\n✓ 140 rows present: {len(df_all) == 140}")
print(f"✓ No missing combos: {len(missing) == 0}")
if missing:
    print("⚠ MISSING:")
    for m in sorted(missing):
        print(f"  {m}")

print("\nNOTE: Training grid used size=2500 instead of 2000 (as executed by A3/T2.1-T2.2).")

# ── Step 3: Save results_all.csv ─────────────────────────────────────────────
os.makedirs('analysis', exist_ok=True)
df_all.to_csv('analysis/results_all.csv', index=False)
print(f"\n✓ Saved analysis/results_all.csv  shape={df_all.shape}")
print(f"  Columns: {list(df_all.columns)}")
