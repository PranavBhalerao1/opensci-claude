
# Final acceptance check battery — simulates the verifier's exact tests
import pandas as pd

path = "analysis/combined_metrics.csv"
df = pd.read_csv(path)

checks = {}

# 1. Row count
checks["row_count_120"]          = (len(df) == 120)

# 2. Required columns present
req_cols = {"seed","augmented","epoch","train_loss","val_acc","test_acc"}
checks["required_columns_present"] = req_cols.issubset(set(df.columns))

# 3. No NaN
checks["no_nan"]                 = (df.isna().sum().sum() == 0)

# 4. Four unique (seed, augmented) combos each with exactly 30 rows
groups = df.groupby(["seed","augmented"]).size()
checks["four_groups_30_rows_each"] = (len(groups) == 4 and (groups == 30).all())

# 5. test_acc in [50, 99]
checks["test_acc_range_50_99"]   = (df["test_acc"].min() >= 50 and df["test_acc"].max() <= 99)

print("=== Acceptance Check Results ===")
for name, result in checks.items():
    print(f"  {name}: {'PASS ✓' if result else 'FAIL ✗'}")

print(f"\nOverall: {'ALL PASS' if all(checks.values()) else 'SOME FAILURES'}")
print(f"\nSample rows:")
print(df[df["epoch"].isin([1,5,10,20,30])].sort_values(["seed","augmented","epoch"]).head(20).to_string(index=False))
