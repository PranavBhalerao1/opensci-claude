
import pandas as pd
import numpy as np

# Load checkpoint stats
ck = pd.read_csv('analysis/checkpoint_stats.csv')
print("checkpoint_stats shape:", ck.shape)
print(ck.to_string())
