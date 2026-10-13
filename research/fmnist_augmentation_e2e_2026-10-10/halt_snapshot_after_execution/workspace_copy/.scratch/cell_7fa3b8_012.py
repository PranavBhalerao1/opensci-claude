
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
import json, os

# ── Load data ─────────────────────────────────────────────────────────────────
gap = pd.read_csv('analysis/gap_trajectory.csv')
with open('analysis/crossover_summary.json') as f:
    cx = json.load(f)

crossover_epoch = cx.get('crossover_epoch', None)   # None = no crossover
epoch5_mean_gap = cx.get('epoch5_mean_gap_pp', -2.70)

print("gap_trajectory shape:", gap.shape)
print(gap.head())
print("crossover_epoch:", crossover_epoch)
print("epoch5_mean_gap:", epoch5_mean_gap)
