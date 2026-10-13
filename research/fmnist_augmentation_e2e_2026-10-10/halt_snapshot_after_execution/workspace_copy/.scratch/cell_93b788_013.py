
import pandas as pd

csv_path = '/tmp/smoke_fix/metrics_seed42_noaug.csv'

# Check the raw file
with open(csv_path) as f:
    lines = f.readlines()
print(f"Total lines: {len(lines)}")
print(f"Line 1: {lines[0].strip()}")
print(f"Line 2: {lines[1].strip()}")

# Check with plain pd.read_csv
df = pd.read_csv(csv_path)
print(f"\npd.read_csv rows: {len(df)}")
print(f"Columns: {df.columns.tolist()}")
print(f"test_acc accessible: {'test_acc' in df.columns}")
print(f"No NaN: {not df.isnull().any().any()}")
print(f"First line starts with '#': {lines[0].startswith('#')}")
print(f"'cuda' in first line... wait, this is CPU smoke test, so:")
print(f"'cpu' or 'device' in first line: {'device' in lines[0]}")
print(f"\nFull first line: {lines[0].strip()}")
