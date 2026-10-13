
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

os.makedirs('figures', exist_ok=True)

df = pd.read_csv('analysis/combined_metrics.csv')

# Extract the four groups
s42_noaug  = df[(df['seed']==42)  & (df['augmented']==False)].sort_values('epoch')
s42_aug    = df[(df['seed']==42)  & (df['augmented']==True)].sort_values('epoch')
s123_noaug = df[(df['seed']==123) & (df['augmented']==False)].sort_values('epoch')
s123_aug   = df[(df['seed']==123) & (df['augmented']==True)].sort_values('epoch')

# Verify all have 30 rows
for name, g in [('s42_noaug', s42_noaug), ('s42_aug', s42_aug),
                ('s123_noaug', s123_noaug), ('s123_aug', s123_aug)]:
    print(f"{name}: {len(g)} rows, epochs {g['epoch'].min()}-{g['epoch'].max()}, "
          f"test_acc@5={g[g['epoch']==5]['test_acc'].values[0]:.2f}, "
          f"test_acc@30={g[g['epoch']==30]['test_acc'].values[0]:.2f}")
