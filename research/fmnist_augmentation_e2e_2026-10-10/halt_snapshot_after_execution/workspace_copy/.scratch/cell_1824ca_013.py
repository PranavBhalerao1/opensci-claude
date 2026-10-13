
# Final file-existence and content check
import os, pandas as pd

for path in ['analysis/gap_trajectory.csv', 'analysis/checkpoint_stats.csv']:
    size = os.path.getsize(path)
    df   = pd.read_csv(path)
    print(f"{path}  size={size}B  rows={len(df)}  cols={len(df.columns)}  NaN={df.isna().sum().sum()}")
    print(f"  columns: {list(df.columns)}")
    if len(df) <= 5:
        print(df.to_string(index=False))
    else:
        print("  head(3):")
        print(df.head(3).to_string(index=False))
        print("  tail(2):")
        print(df.tail(2).to_string(index=False))
    print()
