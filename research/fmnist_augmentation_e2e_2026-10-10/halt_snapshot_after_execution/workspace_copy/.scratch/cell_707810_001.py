
import os, pandas as pd

# Check existing files
print("=== analysis/ directory ===")
for f in sorted(os.listdir('analysis')) if os.path.exists('analysis') else []:
    print(f)

print("\n=== figures/ directory ===")
if os.path.exists('figures'):
    for f in sorted(os.listdir('figures')):
        print(f)
else:
    print("figures/ does not exist")

# Load combined_metrics.csv
df = pd.read_csv('analysis/combined_metrics.csv')
print("\n=== combined_metrics.csv head ===")
print(df.head(10))
print(f"\nShape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print(f"\nGroups (seed, augmented):")
print(df.groupby(['seed', 'augmented']).size())
print(f"\ntest_acc stats:")
print(df['test_acc'].describe())
print(f"\nEpoch range: {df['epoch'].min()} - {df['epoch'].max()}")
