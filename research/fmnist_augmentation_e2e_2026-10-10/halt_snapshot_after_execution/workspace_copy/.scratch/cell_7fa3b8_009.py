
import pandas as pd, os

# Load all required data for SUMMARY.md
ck = pd.read_csv('analysis/checkpoint_stats.csv')
cm = pd.read_csv('analysis/combined_metrics.csv')

# Training dynamics at epoch 5 and 30
def get_dyn(seed, aug_flag, ep):
    row = cm[(cm['seed']==seed) & (cm['augmented']==aug_flag) & (cm['epoch']==ep)]
    return row.iloc[0]['train_loss'], row.iloc[0]['val_acc'], row.iloc[0]['test_acc']

dyn = {}
for seed in [42, 123]:
    for aug_flag, label in [(False,'noaug'),(True,'aug')]:
        for ep in [5, 30]:
            tl, va, ta = get_dyn(seed, aug_flag, ep)
            dyn[(seed,label,ep)] = (tl, va, ta)

for k,v in dyn.items():
    print(k, "->", f"train_loss={v[0]:.4f}, val_acc={v[1]:.2f}, test_acc={v[2]:.2f}")

# Check existing figure paths
import os
figs = sorted([f for f in os.listdir('figures') if not f.startswith('_') and f.endswith('.png')])
print("\nFigure PNGs:", figs)
pdfs = sorted([f for f in os.listdir('figures') if not f.startswith('_') and f.endswith('.pdf')])
print("Figure PDFs:", pdfs)
