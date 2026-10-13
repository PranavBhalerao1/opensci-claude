
import pandas as pd
import numpy as np

# Load all analysis files for cross-validation
combined = pd.read_csv("analysis/combined_metrics.csv")
per_seed = pd.read_csv("analysis/per_seed_accuracy_gap.csv")

print("=== combined_metrics.csv ===")
print(f"Shape: {combined.shape}")
print(combined.dtypes)
print(combined.head(5))
print("Unique columns:", combined.columns.tolist())
