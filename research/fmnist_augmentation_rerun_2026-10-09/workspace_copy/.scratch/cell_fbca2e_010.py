
import pandas as pd
import os

# Load master table
df_all = pd.read_csv('analysis/results_all.csv')
df_ep5 = df_all[df_all['epoch'] == 5].copy()

# ── Step 5: Calibration check ────────────────────────────────────────────────
print("=== Calibration Check: acc_noaug at size=60000 ===")
df_60k_noaug = df_ep5[(df_ep5['size'] == 60000) & (df_ep5['condition'] == 'noaug')]
for _, row in df_60k_noaug.iterrows():
    val = row['test_acc']
    in_range = 0.85 <= val <= 0.93
    status = "✓ OK" if in_range else "⚠ CALIBRATION WARNING"
    print(f"  seed={int(row['seed'])}: acc_noaug={val:.4f}  {status}")

out_of_range = df_60k_noaug[
    (df_60k_noaug['test_acc'] < 0.85) | (df_60k_noaug['test_acc'] > 0.93)
]
if len(out_of_range) > 0:
    print(f"\n⚠ CALIBRATION WARNING: {len(out_of_range)} value(s) outside [0.85, 0.93]:")
    for _, r in out_of_range.iterrows():
        print(f"  seed={int(r['seed'])}, size={int(r['size'])}, acc_noaug={r['test_acc']:.4f}")
else:
    print("\n✓ All acc_noaug at size=60000 within [0.85, 0.93] — no calibration warnings")

# ── Build & save test_acc_summary.csv ────────────────────────────────────────
pivot = df_ep5.pivot_table(index=['size','seed'], columns='condition', values='test_acc')
pivot.columns.name = None
pivot = pivot.reset_index()
pivot = pivot.rename(columns={'aug': 'acc_aug', 'noaug': 'acc_noaug'})
pivot = pivot[['size', 'seed', 'acc_noaug', 'acc_aug']]
pivot.to_csv('analysis/test_acc_summary.csv', index=False)
print(f"\n✓ Saved analysis/test_acc_summary.csv  shape={pivot.shape}")
print(pivot.to_string(index=False))
