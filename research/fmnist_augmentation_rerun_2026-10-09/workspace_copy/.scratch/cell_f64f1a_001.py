
import pandas as pd
import os

# Load the two input files
delta_df = pd.read_csv('analysis/delta_by_size.csv')
results_df = pd.read_csv('analysis/results_all.csv')

print("=== delta_by_size.csv ===")
print(f"Shape: {delta_df.shape}")
print(delta_df.head(10))
print("\nColumns:", delta_df.columns.tolist())

print("\n=== results_all.csv ===")
print(f"Shape: {results_df.shape}")
print(results_df.head(10))
print("\nColumns:", results_df.columns.tolist())
print("\nUnique epochs:", sorted(results_df['epoch'].unique()))
print("Unique sizes:", sorted(results_df['size'].unique()))
print("Unique conditions:", results_df['condition'].unique())
print("Unique seeds:", results_df['seed'].unique())
