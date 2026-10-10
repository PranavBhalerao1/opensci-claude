
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

# ── ensure output dirs ──────────────────────────────────────────────────────
os.makedirs("figures", exist_ok=True)
os.makedirs("paper",   exist_ok=True)
os.makedirs("results", exist_ok=True)

# ── load data ───────────────────────────────────────────────────────────────
acc  = pd.read_csv("analysis/test_acc_summary.csv")
delt = pd.read_csv("analysis/delta_by_size.csv")
with open("analysis/regression_results.json") as f:
    reg = json.load(f)

print("acc shape:", acc.shape)
print(acc.head())
print("\ndelta shape:", delt.shape)
print(delt.head())
print("\nregression keys:", list(reg.keys()))
