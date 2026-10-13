
# Check accuracy gap trajectory for annotations
gap_df = pd.read_csv('analysis/accuracy_gap_trajectory.csv')
print(gap_df.head(10))
print("\nEpoch-5 row:")
print(gap_df[gap_df['epoch'] == 5])
