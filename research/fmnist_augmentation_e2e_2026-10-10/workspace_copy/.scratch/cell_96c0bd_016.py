
# Final summary of what was produced
import os

files = {
    'figures/fig3_loss_curves.png': 'PNG figure, 300 dpi',
    'figures/fig3_loss_curves.pdf': 'PDF vector figure',
    'scripts/fig3_loss_curves.py':  'Plotting script',
}

print("=== Final Artifact Summary ===")
for path, desc in files.items():
    exists = os.path.exists(path)
    size   = os.path.getsize(path) if exists else 0
    print(f"  {'✓' if exists else '✗'}  {path}  ({size/1024:.1f} KB)  — {desc}")

print("\n=== Key Data Points (plotted) ===")
import pandas as pd, json
df = pd.read_csv('analysis/combined_metrics.csv')
with open('analysis/crossover_summary.json') as f:
    cs = json.load(f)

for seed in [42, 123]:
    for aug in [False, True]:
        ep5 = df[(df['seed']==seed)&(df['augmented']==aug)&(df['epoch']==5)].iloc[0]
        print(f"  Seed {seed} {'Aug' if aug else 'NoAug'}  ep5: loss={ep5.train_loss:.4f}, val_acc={ep5.val_acc:.2f}%")

print(f"\nEpoch-5 mean gap: {cs['epoch5_mean_gap_pp']:+.2f} pp")
print(f"Crossover epoch: {cs['crossover_epoch']} (None = no crossover)")
print(f"Regime: {cs['epoch5_regime']}")
