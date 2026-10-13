
import pandas as pd
import io

# Test how pandas reads the leftover CSV files
path = 'data/metrics_seed42_noaug.csv'

# Method 1: plain pd.read_csv
df1 = pd.read_csv(path)
print(f"pd.read_csv(path) → {len(df1)} rows")
print(f"Columns: {df1.columns.tolist()[:3]}")
print(f"First row: {df1.iloc[0].tolist()}")
print()

# Method 2: with comment='#'
df2 = pd.read_csv(path, comment='#')
print(f"pd.read_csv(path, comment='#') → {len(df2)} rows")
print(f"Columns: {df2.columns.tolist()}")
print(f"First row: {df2.iloc[0].tolist()}")
print()

# Method 3: skiprows=1
df3 = pd.read_csv(path, skiprows=1)
print(f"pd.read_csv(path, skiprows=1) → {len(df3)} rows")
print(f"Columns: {df3.columns.tolist()}")
