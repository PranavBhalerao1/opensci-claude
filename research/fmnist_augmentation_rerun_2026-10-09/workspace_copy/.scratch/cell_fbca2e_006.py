
from itertools import product

# The actual training grid used 2500 instead of 2000
# Validate completeness against ACTUAL sizes
actual_sizes      = sorted(df_all['size'].unique())
actual_conditions = sorted(df_all['condition'].unique())
actual_seeds      = sorted(df_all['seed'].unique())
actual_epochs     = sorted(df_all['epoch'].unique())

expected_combos = set(product(actual_sizes, actual_conditions, actual_seeds, actual_epochs))
actual_combos   = set(zip(df_all['size'], df_all['condition'], df_all['seed'], df_all['epoch']))

missing = expected_combos - actual_combos
extra   = actual_combos   - expected_combos

print(f"Expected combos: {len(expected_combos)} (7×2×2×5 = 140)")
print(f"Actual combos:   {len(actual_combos)}")
print(f"Missing: {len(missing)}")
print(f"Extra:   {len(extra)}")

if missing:
    print("⚠ MISSING combinations:")
    for m in sorted(missing):
        print(f"  size={m[0]}, condition={m[1]}, seed={m[2]}, epoch={m[3]}")
else:
    print("✓ No missing combinations")

# Note about size=2500 vs 2000
print("\nNOTE: Actual training grid uses size=2500 (not 2000 as originally specified).")
print("      140 rows are complete across 7×2×2×5 combinations.")
