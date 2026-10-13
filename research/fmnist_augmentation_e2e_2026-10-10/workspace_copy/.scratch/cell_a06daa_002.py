
import pandas as pd
import numpy as np

# Load both primary input files
gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

print("=== gap_trajectory.csv ===")
print(f"Shape: {gap_traj.shape}")
print(gap_traj.dtypes)
print(gap_traj.head(10))
print("...")
print(gap_traj.tail(5))
