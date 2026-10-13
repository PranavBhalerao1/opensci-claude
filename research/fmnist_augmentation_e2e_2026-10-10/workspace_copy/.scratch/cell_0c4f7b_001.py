
import os, pandas as pd

# Check inputs
df = pd.read_csv("analysis/combined_metrics.csv")
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print("Groups:", df.groupby(["seed","augmented"]).size().to_dict())
print(df.head(5))
print("\ntest_acc range:", df["test_acc"].min(), df["test_acc"].max())
