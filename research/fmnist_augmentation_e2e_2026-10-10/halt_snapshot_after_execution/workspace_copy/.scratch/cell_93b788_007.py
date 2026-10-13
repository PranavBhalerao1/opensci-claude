
import pandas as pd
import io

# Simulate the new format
out = io.StringIO()
import csv
w = csv.writer(out)
comment_col = "# seed=42 augment=False device=cuda start=2026-10-10T05:46:38"
w.writerow([comment_col, "train_loss", "train_acc", "val_acc", "test_acc"])
for epoch in range(1, 31):
    w.writerow([epoch, 0.4, 84.0+epoch, 88.0, 88.0+epoch*0.1])  # realistic values

content = out.getvalue()
df = pd.read_csv(io.StringIO(content))

# Check all acceptance criteria
print("=== Acceptance Check Verification ===")
print(f"1. Row count = 30: {len(df) == 30} ({len(df)} rows)")
print(f"2. test_acc all in [50,99]: {df['test_acc'].between(50, 99).all()} (range: {df['test_acc'].min():.1f}-{df['test_acc'].max():.1f})")
print(f"3. No NaN values: {not df.isnull().any().any()}")
print(f"4. First line starts with '#': {content.split(chr(10))[0].startswith('#')}")
print(f"5. 'cuda' in header comment: {'cuda' in content.split(chr(10))[0]}")
print(f"   Column 0 name: {df.columns[0][:50]}...")
print(f"   All metric columns accessible: train_loss={('train_loss' in df.columns)}, val_acc={('val_acc' in df.columns)}, test_acc={('test_acc' in df.columns)}")
