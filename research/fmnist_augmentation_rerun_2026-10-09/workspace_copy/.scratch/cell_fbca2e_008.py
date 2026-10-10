
import pandas as pd
import os

df_all = pd.read_csv('analysis/results_all.csv')

# ── Step 4: Filter epoch==5 and pivot ────────────────────────────────────────
df_ep5 = df_all[df_all['epoch'] == 5].copy()
print(f"Epoch-5 rows: {len(df_ep5)}  (expected 70)")

# test_acc is only populated at epoch 5 (per upstream notes)
print(f"NaN test_acc at epoch 5: {df_ep5['test_acc'].isna().sum()}")
print(df_ep5[['seed','size','condition','test_acc']].head(8))

# Pivot: index=[size,seed], columns=condition, values=test_acc
pivot = df_ep5.pivot_table(index=['size','seed'], columns='condition', values='test_acc')
pivot.columns.name = None
pivot = pivot.reset_index()

# Rename columns to required names
pivot = pivot.rename(columns={'aug': 'acc_aug', 'noaug': 'acc_noaug'})

# Ensure correct column order
pivot = pivot[['size', 'seed', 'acc_noaug', 'acc_aug']]

print(f"\nPivoted shape: {pivot.shape}  (expected 14 rows × 4 cols)")
print(pivot.to_string())
