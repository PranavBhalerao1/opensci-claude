
import pandas as pd
import numpy as np

# Load combined_metrics.csv
df = pd.read_csv('analysis/combined_metrics.csv')
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print("\nHead:")
print(df.head(10))
print("\nTail:")
print(df.tail(5))
print("\nDtypes:")
print(df.dtypes)
print("\nNaN counts:")
print(df.isna().sum())
print("\nUnique seeds:", df['seed'].unique())
print("Unique augmented:", df['augmented'].unique())
print("Epoch range:", df['epoch'].min(), "-", df['epoch'].max())
print("Groups (seed, augmented) counts:")
print(df.groupby(['seed','augmented']).size())
