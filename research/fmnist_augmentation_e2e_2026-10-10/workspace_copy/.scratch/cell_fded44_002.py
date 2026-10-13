
import pandas as pd

df = pd.read_csv('analysis/gap_trajectory.csv')
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print(df.head(10))
print("\nDescribe:")
print(df.describe())
