
import pandas as pd, json

# Load and inspect the combined metrics
df = pd.read_csv('analysis/combined_metrics.csv')
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print(df.head(10))
print("\nUnique groups:")
print(df.groupby(['seed','augmented']).size().reset_index(name='rows'))
print("\nTest accuracy range:", df['test_acc'].min(), "–", df['test_acc'].max())

# Load crossover summary
with open('analysis/crossover_summary.json') as f:
    cx = json.load(f)
print("\nCrossover summary:", json.dumps(cx, indent=2))
