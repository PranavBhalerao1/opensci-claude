
import os, pandas as pd

# Check existing CSVs
for name in ['metrics_seed42_noaug.csv','metrics_seed42_aug.csv','metrics_seed123_noaug.csv','metrics_seed123_aug.csv']:
    path = f'data/{name}'
    if os.path.exists(path):
        # Read comment header
        with open(path) as f:
            lines = f.readlines()
        print(f"\n=== {name} ===")
        print(f"  Header: {lines[0].strip()}")
        print(f"  Total lines: {len(lines)}")
        # Read as dataframe
        df = pd.read_csv(path, comment='#')
        print(f"  DataFrame rows: {len(df)}")
        print(f"  Columns: {list(df.columns)}")
        print(f"  test_acc range: [{df['test_acc'].min():.4f}, {df['test_acc'].max():.4f}]")
        print(f"  First row epoch: {df['epoch'].iloc[0]}, Last row epoch: {df['epoch'].iloc[-1]}")
    else:
        print(f"{name}: NOT FOUND")
