
import pandas as pd
import pathlib, os

# ── 1. Read with pandas (plain, no comment= kwarg) ──────────────────────────
csv_path = "data/metrics_seed42_aug.csv"
df = pd.read_csv(csv_path)

print("=== Raw column names ===")
for c in df.columns:
    print(f"  {repr(c)}")

print(f"\nShape: {df.shape}")
print(f"\nFirst 3 rows:\n{df.head(3)}")
