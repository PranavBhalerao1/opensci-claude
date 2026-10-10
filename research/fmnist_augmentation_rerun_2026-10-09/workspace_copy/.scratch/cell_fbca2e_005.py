
import pandas as pd

df42  = pd.read_csv('results/results_seed42.csv')
df123 = pd.read_csv('results/results_seed123.csv')
df_all = pd.concat([df42, df123], ignore_index=True)

# Check actual sizes present in data
print("Actual sizes in data:", sorted(df_all['size'].unique()))
print("Actual conditions:",    sorted(df_all['condition'].unique()))
print("Actual seeds:",         sorted(df_all['seed'].unique()))
print("Actual epochs:",        sorted(df_all['epoch'].unique()))
print()

actual_sizes = sorted(df_all['size'].unique())
print(f"7 distinct sizes present: {len(actual_sizes) == 7}")
print(f"2 conditions present:     {len(df_all['condition'].unique()) == 2}")
print(f"2 seeds present:          {len(df_all['seed'].unique()) == 2}")
print(f"5 epochs present:         {len(df_all['epoch'].unique()) == 5}")
