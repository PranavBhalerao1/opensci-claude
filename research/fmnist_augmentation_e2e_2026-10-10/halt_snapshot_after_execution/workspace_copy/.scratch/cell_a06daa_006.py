
import pandas as pd
import numpy as np

gap_traj = pd.read_csv("analysis/gap_trajectory.csv")
ckpt_stats = pd.read_csv("analysis/checkpoint_stats.csv")

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.float_format', '{:.6f}'.format)
print("=== checkpoint_stats.csv (full) ===")
print(ckpt_stats.to_string())

print("\n=== gap_trajectory.csv (full) ===")
print(gap_traj.to_string())
