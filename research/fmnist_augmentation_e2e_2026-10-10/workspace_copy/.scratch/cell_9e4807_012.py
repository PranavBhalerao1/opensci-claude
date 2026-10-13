
import pandas as pd
import os
import glob

print("=" * 70)
print("VERIFICATION: All four training runs")
print("=" * 70)

csv_files = {
    'seed42_noaug':  'data/metrics_seed42_noaug.csv',
    'seed42_aug':    'data/metrics_seed42_aug.csv',
    'seed123_noaug': 'data/metrics_seed123_noaug.csv',
    'seed123_aug':   'data/metrics_seed123_aug.csv',
}

all_ok = True
results = {}

for name, path in csv_files.items():
    print(f"\n--- {name} ---")
    if not os.path.exists(path):
        print(f"  ✗ FILE NOT FOUND: {path}")
        all_ok = False
        continue
    
    # Check raw file structure
    with open(path) as f:
        lines = f.readlines()
    print(f"  File size: {os.path.getsize(path)} bytes")
    print(f"  Total lines: {len(lines)}")
    print(f"  Line 0 (comment): {lines[0].rstrip()}")
    print(f"  Line 1 (header): {lines[1].rstrip()}")
    print(f"  First data: {lines[2].rstrip()}")
    print(f"  Last data: {lines[-1].rstrip()}")
    
    # Check comment contains 'cuda'
    comment_ok = lines[0].startswith('#') and 'cuda' in lines[0].lower()
    print(f"  Comment has CUDA: {'✓' if comment_ok else '✗'} [{lines[0].strip()[:60]}]")
    
    # Read with comment='#'
    df = pd.read_csv(path, comment='#')
    n_rows = len(df)
    print(f"\n  pd.read_csv(comment='#'): {n_rows} rows")
    print(f"  Columns: {list(df.columns)}")
    
    # Check row count
    row_ok = (n_rows == 30)
    print(f"  30 rows: {'✓' if row_ok else f'✗ ({n_rows} rows)'}")
    
    # Check epoch range
    epoch_ok = (df['epoch'].iloc[0] == 1 and df['epoch'].iloc[-1] == 30)
    print(f"  Epoch 1..30: {'✓' if epoch_ok else f'✗ (range {df[\"epoch\"].min()}..{df[\"epoch\"].max()})'}")
    
    # Check test_acc range [50, 99]
    test_acc_min = df['test_acc'].min()
    test_acc_max = df['test_acc'].max()
    acc_ok = df['test_acc'].between(50, 99).all()
    print(f"  test_acc in [50,99]: {'✓' if acc_ok else '✗'} (range [{test_acc_min:.2f}, {test_acc_max:.2f}])")
    
    # Check val_acc range
    val_acc_ok = df['val_acc'].between(50, 99).all()
    print(f"  val_acc in [50,99]: {'✓' if val_acc_ok else '✗'} (range [{df['val_acc'].min():.2f}, {df['val_acc'].max():.2f}])")
    
    # Check no NaN
    nan_ok = not df.isnull().any().any()
    print(f"  No NaN: {'✓' if nan_ok else '✗'}")
    
    # Key metrics
    ep5_test  = df[df['epoch'] == 5]['test_acc'].values[0]
    ep30_test = df[df['epoch'] == 30]['test_acc'].values[0]
    print(f"\n  Epoch-5  test_acc: {ep5_test:.2f}%")
    print(f"  Epoch-30 test_acc: {ep30_test:.2f}%")
    
    # Also check naive read
    df_naive = pd.read_csv(path)
    print(f"\n  pd.read_csv() (naive): {len(df_naive)} rows, {len(df_naive.columns)} cols")
    
    # Non-empty line counting
    non_empty = [l for l in lines if l.strip()]
    print(f"  Non-empty lines: {len(non_empty)} (minus 1 = {len(non_empty)-1}, minus 2 = {len(non_empty)-2})")
    
    run_ok = row_ok and epoch_ok and acc_ok and nan_ok and comment_ok and val_acc_ok
    print(f"\n  {'✓ PASS' if run_ok else '✗ FAIL'}")
    
    results[name] = {
        'ep5_test': ep5_test, 'ep30_test': ep30_test,
        'rows': n_rows, 'ok': run_ok
    }
    all_ok = all_ok and run_ok

print("\n" + "=" * 70)
print(f"Overall CSV check: {'✓ ALL PASS' if all_ok else '✗ SOME FAILED'}")
