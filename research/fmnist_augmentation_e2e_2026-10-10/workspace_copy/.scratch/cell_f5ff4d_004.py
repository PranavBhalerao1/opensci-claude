
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np
import os, pathlib

# ── ensure output directory exists ──────────────────────────────────────────
pathlib.Path('figures').mkdir(exist_ok=True)

# ── load data ────────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/gap_trajectory.csv')
print("Data loaded:", df.shape)
print(df[['epoch','gap_seed42','gap_seed123','mean_gap']].to_string(index=False))

epochs     = df['epoch'].values
gap_s42    = df['gap_seed42'].values
gap_s123   = df['gap_seed123'].values
mean_gap   = df['mean_gap'].values

epoch5_idx = df.index[df['epoch'] == 5][0]
ep5_s42    = gap_s42[epoch5_idx]
ep5_s123   = gap_s123[epoch5_idx]
ep5_mean   = mean_gap[epoch5_idx]

crossover_epoch = None   # confirmed: no crossover within 30 epochs

print(f"\nEpoch-5: seed42={ep5_s42}, seed123={ep5_s123}, mean={ep5_mean}")
print(f"Crossover epoch: {crossover_epoch}")
