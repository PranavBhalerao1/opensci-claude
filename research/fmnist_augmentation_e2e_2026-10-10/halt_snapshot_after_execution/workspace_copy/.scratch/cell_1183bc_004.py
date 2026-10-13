
import pandas as pd, json

gap_df = pd.read_csv('analysis/accuracy_gap_trajectory.csv')
print(gap_df.head(10))
print("\nEpoch-5 row:")
print(gap_df[gap_df['epoch'] == 5])
print("\nPer-seed gap:")
ps = pd.read_csv('analysis/per_seed_accuracy_gap.csv')
print(ps.head(10))
