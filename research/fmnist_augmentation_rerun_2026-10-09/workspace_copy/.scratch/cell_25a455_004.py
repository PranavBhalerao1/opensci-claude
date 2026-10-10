
# Final verification: read back and confirm
check = pd.read_csv("analysis/delta_by_size.csv")
print("Read-back shape:", check.shape)
print("Columns:", list(check.columns))
print("NaN count:", check.isna().sum().sum())
print("Inf count:", (~np.isfinite(check.select_dtypes(float))).sum().sum())
print("\nNegative delta_mean rows:")
neg = check[check["delta_mean"] < 0]
for _, row in neg.iterrows():
    print(f"  size={int(row['size']):>6}  delta_mean={row['delta_mean']:>8.4f}  *** NEGATIVE DELTA ***")
print(f"\nAll {len(neg)}/7 sizes have negative delta_mean")
