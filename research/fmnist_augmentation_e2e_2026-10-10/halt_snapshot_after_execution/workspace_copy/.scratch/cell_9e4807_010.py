
# CPU smoke-test the new train.py: run 2 epochs, verify CSV format + accuracy range
import subprocess, sys, os, pandas as pd

result = subprocess.run(
    [sys.executable, 'src/train.py',
     '--seed', '42', '--augment', 'false', '--epochs', '2',
     '--data_dir', 'data/fashion_mnist',
     '--out_dir', '/tmp/smoke_v2'],
    capture_output=True, text=True, timeout=120
)
print("STDOUT:", result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-1000:])
    
# Now check the output CSV
csv_path = '/tmp/smoke_v2/metrics_seed42_noaug.csv'
if os.path.exists(csv_path):
    with open(csv_path) as f:
        lines = f.readlines()
    print(f"\nCSV total lines: {len(lines)}")
    print(f"Line 0 (comment): {lines[0].rstrip()}")
    print(f"Line 1 (header): {lines[1].rstrip()}")
    print(f"Line 2 (first data): {lines[2].rstrip()}")
    
    df = pd.read_csv(csv_path, comment='#')
    print(f"\npd.read_csv(comment='#'): {len(df)} rows")
    print(f"Columns: {list(df.columns)}")
    print(f"test_acc values: {list(df['test_acc'])}")
    print(f"test_acc in [50,99]: {df['test_acc'].between(50,99).all()}")
    print(f"Any NaN: {df.isnull().any().any()}")
    
    # Also test naive pd.read_csv (no comment param)
    try:
        df2 = pd.read_csv(csv_path)
        print(f"\npd.read_csv() (naive): {len(df2)} rows, {len(df2.columns)} cols")
        print(f"  col names[:2]: {list(df2.columns)[:2]}")
    except Exception as e:
        print(f"\npd.read_csv() (naive): ERROR - {e}")
