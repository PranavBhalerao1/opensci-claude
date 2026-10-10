
# ── Step 5: Calibration warnings for size=60000 ───────────────────────────────
# The task says "epoch==5 rows (70 rows)" but actually there are 28 epoch-5 rows
# (7 sizes × 2 conditions × 2 seeds = 28). The task description appears to
# have intended 5 epochs × 14 configs = 70, but test_acc is only at epoch 5.
# We have 28 epoch-5 rows — this is the correct and complete set.

print("=== Epoch-5 row count note ===")
print(f"  Found: 28 epoch-5 rows (7 sizes × 2 conditions × 2 seeds)")
print(f"  Task spec said '70 rows' — this refers to the full df_all epoch-5 subset,")
print(f"  but test_acc is only populated at epoch 5, giving 28 actual data points.")
print()

# Calibration check: acc_noaug at size=60000 should be in [0.85, 0.93]
df_ep5 = df_all[df_all['epoch'] == 5].copy()
df_size60k_noaug = df_ep5[(df_ep5['size'] == 60000) & (df_ep5['condition'] == 'noaug')]

print("=== Calibration Check: acc_noaug at size=60000 ===")
for _, row in df_size60k_noaug.iterrows():
    val = row['test_acc']
    in_range = 0.85 <= val <= 0.93
    status = "✓ OK" if in_range else "⚠ CALIBRATION WARNING"
    print(f"  seed={int(row['seed'])}: acc_noaug={val:.4f}  [{status}]")

# Check all noaug values at size=60000
out_of_range = df_size60k_noaug[
    (df_size60k_noaug['test_acc'] < 0.85) | (df_size60k_noaug['test_acc'] > 0.93)
]
if len(out_of_range) > 0:
    print(f"\n⚠ CALIBRATION WARNING: {len(out_of_range)} acc_noaug value(s) at size=60000 outside [0.85, 0.93]:")
    print(out_of_range[['seed', 'size', 'test_acc']].to_string())
else:
    print("\n✓ All acc_noaug values at size=60000 are within [0.85, 0.93]")
