
import pandas as pd
import io

# Format: # comment (single field) + 30 epoch rows (5 fields each), NO col-names
test_csv_noheader = """# seed=42 augment=False device=cuda start=2026-10-10T04:44:44
1,0.5,88.0,91.0,90.0
2,0.4,89.0,91.5,90.5
3,0.35,90.0,92.0,91.0
"""

print("=== Comment + epoch rows, NO col-names, pd.read_csv() ===")
try:
    df = pd.read_csv(io.StringIO(test_csv_noheader))
    print(f"  rows={len(df)}, cols={list(df.columns)}")
    print(df.to_string())
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}")

print("\n=== Comment + epoch rows, NO col-names, pd.read_csv(comment='#') ===")
try:
    df = pd.read_csv(io.StringIO(test_csv_noheader), comment='#')
    print(f"  rows={len(df)}, cols={list(df.columns)}")
    print(df.head())
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {str(e)[:200]}")

# Also test: col-names line with inline comment, 30 data rows
test_csv_inline = """epoch,train_loss,train_acc,val_acc,test_acc
1,0.5,88.0,91.0,90.0
2,0.4,89.0,91.5,90.5
3,0.35,90.0,92.0,91.0
"""

print("\n=== Standard format (no comment), pd.read_csv() ===")
df = pd.read_csv(io.StringIO(test_csv_inline))
print(f"  rows={len(df)}, cols={list(df.columns)}")
print(f"  test_acc values: {list(df['test_acc'])}")
print(f"  Any NaN: {df.isnull().any().any()}")
