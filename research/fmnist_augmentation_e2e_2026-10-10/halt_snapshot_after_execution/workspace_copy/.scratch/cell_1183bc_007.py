
# Final provenance summary print
import datetime, pandas as pd

df = pd.read_csv('analysis/combined_metrics.csv')
print("=== Provenance & Data Summary ===")
print(f"Source:    analysis/combined_metrics.csv  ({df.shape[0]} rows × {df.shape[1]} cols)")
print(f"Accessed:  {datetime.date.today()}")
print()
print("Lines plotted:")
rows = []
for (seed, aug), grp in df.groupby(['seed','augmented']):
    grp = grp.sort_values('epoch')
    acc_ep5  = grp[grp.epoch==5 ].test_acc.values[0]
    acc_ep30 = grp[grp.epoch==30].test_acc.values[0]
    style = 'solid' if seed==42 else 'dashed'
    color = 'blue' if not aug else 'orange'
    print(f"  seed={seed:<3d}, aug={str(aug):<5s} → color={color}, style={style}, "
          f"acc@ep5={acc_ep5:.2f}%, acc@ep30={acc_ep30:.2f}%")

print()
print("Output artifacts:")
import os
for p in ['figures/fig1_test_accuracy_curves.png', 'figures/fig1_test_accuracy_curves.pdf']:
    print(f"  {p}  ({os.path.getsize(p)/1024:.1f} KB)")
