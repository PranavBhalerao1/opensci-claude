
# Verify the exact structure of the stale CSVs
with open('data/metrics_seed42_noaug.csv') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print(f"Line 0 (comment): {lines[0].rstrip()}")
print(f"Line 1 (header): {lines[1].rstrip()}")
print(f"Line 2 (first data): {lines[2].rstrip()}")
print(f"Line 3 (data row 2): {lines[3].rstrip()}")
print(f"Last line ({len(lines)-1}): {lines[-1].rstrip()}")

# Count non-empty lines
non_empty = [l for l in lines if l.strip()]
print(f"\nNon-empty lines: {len(non_empty)}")
print(f"Non-empty lines - 1: {len(non_empty) - 1}")
print(f"Non-empty lines - 2: {len(non_empty) - 2}")

# Check what different pandas read methods give
import pandas as pd

df_comment = pd.read_csv('data/metrics_seed42_noaug.csv', comment='#')
print(f"\npd.read_csv(comment='#'): {len(df_comment)} rows")
print(f"  columns: {list(df_comment.columns)}")
print(f"  first epoch: {df_comment['epoch'].iloc[0]}, last: {df_comment['epoch'].iloc[-1]}")
print(f"  test_acc range: [{df_comment['test_acc'].min():.4f}, {df_comment['test_acc'].max():.4f}]")

try:
    df_plain = pd.read_csv('data/metrics_seed42_noaug.csv')
    print(f"\npd.read_csv(): {len(df_plain)} rows")
    print(f"  columns: {list(df_plain.columns)[:2]}...")
except Exception as e:
    print(f"\npd.read_csv(): ERROR - {e}")
