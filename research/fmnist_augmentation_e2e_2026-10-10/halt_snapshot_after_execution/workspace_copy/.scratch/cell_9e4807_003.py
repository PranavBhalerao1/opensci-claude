
import pandas as pd
import io

# Simulate current file format
sample_csv = """# seed=42 augment=False device=cuda start=2026-10-10T04:44:44
epoch,train_loss,train_acc,val_acc,test_acc
1,0.5,0.82,0.88,0.87
2,0.4,0.85,0.90,0.89
3,0.35,0.87,0.91,0.90
"""

print("=== With comment='#' ===")
try:
    df1 = pd.read_csv(io.StringIO(sample_csv), comment='#')
    print(f"  rows={len(df1)}, cols={list(df1.columns)}")
    print(f"  dtypes: {dict(df1.dtypes)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Without comment handling (default) ===")
try:
    df2 = pd.read_csv(io.StringIO(sample_csv))
    print(f"  rows={len(df2)}, cols={list(df2.columns)[:3]}...")
    print(f"  dtypes: {dict(df2.dtypes)}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

print("\n=== With on_bad_lines='skip' ===")
try:
    df3 = pd.read_csv(io.StringIO(sample_csv), on_bad_lines='skip')
    print(f"  rows={len(df3)}, cols={list(df3.columns)[:3]}...")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# Now try the 31-row scenario: what if epoch 0 was also written?
sample_csv_31 = """# seed=42 augment=False device=cuda start=2026-10-10T04:44:44
epoch,train_loss,train_acc,val_acc,test_acc
0,0.6,0.78,0.85,0.84
1,0.5,0.82,0.88,0.87
2,0.4,0.85,0.90,0.89
"""

print("\n=== 31-row format with comment='#' ===")
try:
    df4 = pd.read_csv(io.StringIO(sample_csv_31), comment='#')
    print(f"  rows={len(df4)}, first epoch={df4['epoch'].iloc[0]}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# Pandas version
print(f"\npandas version: {pd.__version__}")
