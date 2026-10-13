
import pandas as pd
import io

test_csv = """epoch,train_loss,train_acc,val_acc,test_acc
1,0.5,88.0,91.0,90.0
2,0.4,89.0,91.5,90.5
3,0.35,90.0,92.0,91.0
# seed=42 augment=False device=cuda start=2026-10-10T04:44:44
"""

df = pd.read_csv(io.StringIO(test_csv))
print("With trailing # comment, pd.read_csv():")
print(df.to_string())
print(f"\nAny NaN: {df.isnull().any().any()}")
print(f"test_acc dtype: {df['test_acc'].dtype}")
print(f"test_acc values: {list(df['test_acc'])}")
print(f"\nTotal rows: {len(df)}")
