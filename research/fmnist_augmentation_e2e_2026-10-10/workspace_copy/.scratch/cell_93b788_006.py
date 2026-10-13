
# Demonstrate the fix: combine the # comment with column names in a single header line
import pandas as pd
import csv
import io

# Proposed fix: comment IS the first column name (starts with #)
out = io.StringIO()
w = csv.writer(out)
comment_col = "# seed=42 augment=False device=cuda start=2026-10-10T05:46:38"
w.writerow([comment_col, "train_loss", "train_acc", "val_acc", "test_acc"])
for epoch in range(1, 31):
    w.writerow([epoch, 0.4, 84.0, 88.0, 88.0])

content = out.getvalue()
print("First line:", content.split('\n')[0])
print("Second line:", content.split('\n')[1])

df = pd.read_csv(io.StringIO(content))
print(f"\npd.read_csv rows: {len(df)}")
print(f"Columns: {df.columns.tolist()}")
print(f"df['test_acc'] exists: {'test_acc' in df.columns}")
print(f"NaN values: {df.isnull().any().any()}")
print(f"First line starts with '#': {content.split(chr(10))[0].startswith('#')}")
print(f"'cuda' in first line: {'cuda' in content.split(chr(10))[0]}")
