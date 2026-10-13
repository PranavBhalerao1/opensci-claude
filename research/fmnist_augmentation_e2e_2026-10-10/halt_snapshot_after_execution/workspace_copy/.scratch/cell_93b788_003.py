
import pandas as pd

for name in ['data/metrics_seed42_noaug.csv', 'data/metrics_seed42_aug.csv',
             'data/metrics_seed123_noaug.csv', 'data/metrics_seed123_aug.csv']:
    try:
        with open(name) as f:
            lines = f.readlines()
        print(f"\n=== {name} ===")
        print(f"Total lines: {len(lines)}")
        print(f"First 3 lines: {lines[:3]}")
        print(f"Last 2 lines: {lines[-2:]}")
    except FileNotFoundError:
        print(f"NOT FOUND: {name}")
