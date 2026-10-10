
# ── Final verification of all acceptance checks ───────────────────────────────
import pandas as pd
import os

print("=" * 60)
print("ACCEPTANCE CHECK VERIFICATION")
print("=" * 60)

# Check 1: results_all.csv has exactly 140 data rows
df_all = pd.read_csv('analysis/results_all.csv')
check1 = len(df_all) == 140
print(f"\n[1] results_all.csv has 140 rows: {check1}  (actual: {len(df_all)})")
print(f"    Columns: {list(df_all.columns)}")

# Check 2: test_acc_summary.csv has exactly 14 rows
df_sum = pd.read_csv('analysis/test_acc_summary.csv')
check2 = len(df_sum) == 14
print(f"\n[2] test_acc_summary.csv has 14 rows: {check2}  (actual: {len(df_sum)})")

# Check 3: test_acc_summary.csv has correct columns
expected_cols = {'size', 'seed', 'acc_noaug', 'acc_aug'}
check3 = expected_cols == set(df_sum.columns)
print(f"\n[3] test_acc_summary.csv has correct columns: {check3}")
print(f"    Columns: {list(df_sum.columns)}")

# Check 4: No missing (size, condition, seed) at epoch 5
df_ep5 = df_all[df_all['epoch'] == 5]
from itertools import product
actual_sizes      = sorted(df_all['size'].unique())
actual_conditions = sorted(df_all['condition'].unique())
actual_seeds      = sorted(df_all['seed'].unique())
expected_ep5 = set(product(actual_sizes, actual_conditions, actual_seeds))
actual_ep5   = set(zip(df_ep5['size'], df_ep5['condition'], df_ep5['seed']))
check4 = expected_ep5 == actual_ep5
print(f"\n[4] No missing (size, condition, seed) at epoch 5: {check4}")
print(f"    Expected: {len(expected_ep5)}  Found: {len(actual_ep5)}")

# Check 5: gpu_device_info.txt is non-empty and has CUDA device name
with open('analysis/gpu_device_info.txt', 'r') as f:
    gpu_content = f.read()
check5 = len(gpu_content) > 0 and 'NVIDIA' in gpu_content
print(f"\n[5] gpu_device_info.txt non-empty with CUDA device: {check5}")
print(f"    File size: {len(gpu_content)} chars, Contains 'NVIDIA': {'NVIDIA' in gpu_content}")

print("\n" + "=" * 60)
all_pass = all([check1, check2, check3, check4, check5])
print(f"ALL CHECKS PASSED: {all_pass}")
print("=" * 60)

# Summary stats
print(f"\n=== Summary Statistics ===")
print(f"Sizes tested: {actual_sizes}")
print(f"\ntest_acc_summary stats:")
print(df_sum[['acc_noaug','acc_aug']].describe().round(4))
