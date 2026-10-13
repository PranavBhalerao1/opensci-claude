
import pathlib, re, textwrap
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ── 1. Load data ──────────────────────────────────────────────────────────────
df = pd.read_csv('analysis/gap_trajectory.csv')
print("gap_trajectory.csv shape:", df.shape)
print(df[df['epoch'].isin([5, 10, 20, 30])])

# ── 2. Parse crossover_report.txt ─────────────────────────────────────────────
report_text = pathlib.Path('analysis/crossover_report.txt').read_text()

# Look for "CROSSOVER EPOCH: No crossover" or a specific epoch number
no_cross_match  = re.search(r'CROSSOVER EPOCH:\s*No crossover', report_text, re.IGNORECASE)
epoch_match     = re.search(r'CROSSOVER EPOCH:\s*(\d+)', report_text, re.IGNORECASE)

if no_cross_match:
    crossover_epoch = None
    print("Crossover: None (no crossover within 30 epochs)")
elif epoch_match:
    crossover_epoch = int(epoch_match.group(1))
    print(f"Crossover epoch: {crossover_epoch}")
else:
    crossover_epoch = None
    print("Could not parse crossover epoch – defaulting to None")
