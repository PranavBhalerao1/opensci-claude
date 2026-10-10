
import os, pandas as pd

df = pd.read_csv("analysis/results_all.csv")
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print(df.head(10))
print("\nUnique sizes:", sorted(df['size'].unique()))
print("Unique conditions:", df['condition'].unique())
print("Unique seeds:", df['seed'].unique())
print("Unique epochs:", sorted(df['epoch'].unique()))
print("\nSample stats:\n", df.describe())
