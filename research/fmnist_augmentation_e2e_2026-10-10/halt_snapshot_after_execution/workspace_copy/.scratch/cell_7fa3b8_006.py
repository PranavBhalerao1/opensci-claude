
import pandas as pd
import numpy as np
import os

os.makedirs('results', exist_ok=True)

# ── Load checkpoint stats ─────────────────────────────────────────────────────
ck = pd.read_csv('analysis/checkpoint_stats.csv')

# ── Step 1: Format values to 2 dp as strings ─────────────────────────────────
def fmt_acc(v):
    return f"{v:.2f}"

def fmt_gap(v):
    sign = '+' if v >= 0 else '−'   # use proper minus sign
    return f"{sign}{abs(v):.2f}"

rows = []
for _, r in ck.iterrows():
    rows.append({
        'epoch':           int(r['epoch']),
        'noaug_s42_test':  fmt_acc(r['noaug_s42_test']),
        'aug_s42_test':    fmt_acc(r['aug_s42_test']),
        'gap_s42':         fmt_gap(r['gap_s42']),
        'noaug_s123_test': fmt_acc(r['noaug_s123_test']),
        'aug_s123_test':   fmt_acc(r['aug_s123_test']),
        'gap_s123':        fmt_gap(r['gap_s123']),
        'mean_gap':        fmt_gap(r['mean_gap']),
    })

df_table = pd.DataFrame(rows, columns=[
    'epoch','noaug_s42_test','aug_s42_test','gap_s42',
    'noaug_s123_test','aug_s123_test','gap_s123','mean_gap'
])

print("Table shape:", df_table.shape)
print(df_table.to_string(index=False))

# ── Step 2: Write CSV ─────────────────────────────────────────────────────────
df_table.to_csv('analysis/table1_checkpoint_summary.csv', index=False)
print("\nWrote analysis/table1_checkpoint_summary.csv")

# Verify
verify = pd.read_csv('analysis/table1_checkpoint_summary.csv')
print("Verification rows:", len(verify), "| columns:", list(verify.columns))
