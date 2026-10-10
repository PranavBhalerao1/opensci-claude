
import pandas as pd
import numpy as np
import os

# ── 1. Load ──────────────────────────────────────────────────────────────────
df = pd.read_csv("analysis/test_acc_summary.csv")
print("Loaded shape:", df.shape)
print(df.to_string(index=False))
