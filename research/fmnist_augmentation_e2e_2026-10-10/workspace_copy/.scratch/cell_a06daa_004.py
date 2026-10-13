
import pandas as pd
import numpy as np

gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

print("=== gap_trajectory.csv ===")
print(f"Shape: {gap_traj.shape}")
print(gap_traj.head())

print("\n=== checkpoint_stats.csv ===")
print(f"Shape: {ckpt_stats.shape}")
print(ckpt_stats.dtypes)
print(ckpt_stats)
