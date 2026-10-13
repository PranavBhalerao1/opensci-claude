
import pandas as pd
import os
import torch

print("=" * 60)
print("VERIFICATION: All 4 CSV Files")
print("=" * 60)

csvs = {
    'seed42_noaug': 'data/metrics_seed42_noaug.csv',
    'seed42_aug':   'data/metrics_seed42_aug.csv',
    'seed123_noaug':'data/metrics_seed123_noaug.csv',
    'seed123_aug':  'data/metrics_seed123_aug.csv',
}

all_passed = True
for name, path in csvs.items():
    print(f"\n--- {name} ---")
    
    # Check file exists
    assert os.path.exists(path), f"MISSING: {path}"
    
    # Read raw lines
    with open(path) as f:
        lines = f.readlines()
    print(f"  Total lines: {len(lines)}")
    print(f"  Line 1: {lines[0].strip()[:80]}")
    
    # pd.read_csv (no comment param — verifier's method)
    df = pd.read_csv(path)
    n_rows = len(df)
    has_nan = df.isnull().any().any()
    test_acc_ok = df['test_acc'].between(50, 99).all()
    first_line = lines[0].strip()
    has_hash = first_line.startswith('#')
    has_cuda = 'cuda' in first_line.lower()
    
    ep5_test   = df['test_acc'].iloc[4]   # 0-indexed: index 4 = epoch 5
    ep30_test  = df['test_acc'].iloc[-1]  # last row = epoch 30
    
    print(f"  pd.read_csv rows: {n_rows} {'✓' if n_rows==30 else '✗ FAIL'}")
    print(f"  NaN values: {has_nan} {'✓' if not has_nan else '✗ FAIL'}")
    print(f"  test_acc in [50,99]: {test_acc_ok} {'✓' if test_acc_ok else '✗ FAIL'}")
    print(f"  header starts with #: {has_hash} {'✓' if has_hash else '✗ FAIL'}")
    print(f"  header contains 'cuda': {has_cuda} {'✓' if has_cuda else '✗ FAIL'}")
    print(f"  Epoch-5 test_acc={ep5_test:.2f}%, Epoch-30 test_acc={ep30_test:.2f}%")
    
    if not all([n_rows==30, not has_nan, test_acc_ok, has_hash, has_cuda]):
        all_passed = False

print(f"\n{'='*60}")
print(f"All CSV checks passed: {all_passed}")
