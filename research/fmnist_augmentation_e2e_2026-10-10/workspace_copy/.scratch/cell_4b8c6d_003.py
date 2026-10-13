
import pandas as pd

# Verify all four CSVs produce 30 rows each with plain pd.read_csv
configs = [
    ("data/metrics_seed42_noaug.csv",  42,  False),
    ("data/metrics_seed42_aug.csv",    42,  True),
    ("data/metrics_seed123_noaug.csv", 123, False),
    ("data/metrics_seed123_aug.csv",   123, True),
]

for path, seed, aug in configs:
    df = pd.read_csv(path)
    print(f"{path}: shape={df.shape}, cols={df.columns.tolist()}")
