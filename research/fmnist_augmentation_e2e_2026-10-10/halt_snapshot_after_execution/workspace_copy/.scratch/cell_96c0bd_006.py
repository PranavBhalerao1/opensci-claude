
# Check accuracy_gap_trajectory for more context
import pandas as pd
gap_df = pd.read_csv('analysis/accuracy_gap_trajectory.csv')
print(gap_df.head(10))
print("\nColumns:", gap_df.columns.tolist())
print("Shape:", gap_df.shape)
