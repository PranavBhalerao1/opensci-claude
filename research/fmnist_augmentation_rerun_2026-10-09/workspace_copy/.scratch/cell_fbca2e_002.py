
import pandas as pd

# Load both seed files
df42  = pd.read_csv('results/results_seed42.csv')
df123 = pd.read_csv('results/results_seed123.csv')

print("=== Seed 42 ===")
print(f"Shape: {df42.shape}")
print(df42.head(3))
print(df42.dtypes)

print("\n=== Seed 123 ===")
print(f"Shape: {df123.shape}")
print(df123.head(3))
print(df123.dtypes)
