
import os, pandas as pd

print("=" * 65)
print("FINAL ACCEPTANCE CHECKS")
print("=" * 65)

# 1. table1_checkpoint_summary.csv ─ exists and has 4 rows
csv_path = 'analysis/table1_checkpoint_summary.csv'
assert os.path.exists(csv_path), "FAIL: CSV not found"
df_csv = pd.read_csv(csv_path)
assert len(df_csv) == 4, f"FAIL: CSV has {len(df_csv)} rows, expected 4"
print(f"✓ analysis/table1_checkpoint_summary.csv  — {len(df_csv)} rows")
print(df_csv.to_string(index=False))

# 2. table1_checkpoint_summary.tex ─ exists + contains \begin{tabular} & \end{tabular}
tex_path = 'analysis/table1_checkpoint_summary.tex'
assert os.path.exists(tex_path), "FAIL: TeX not found"
tex = open(tex_path).read()
assert r'\begin{tabular}' in tex, "FAIL: missing \\begin{tabular}"
assert r'\end{tabular}'   in tex, "FAIL: missing \\end{tabular}"
print(f"\n✓ analysis/table1_checkpoint_summary.tex  — \\begin{{tabular}} and \\end{{tabular}} present")

# 3. results/SUMMARY.md ─ exists + contains 'epoch-5', 'regime', numeric gap, fig1/2/3 paths
md_path = 'results/SUMMARY.md'
assert os.path.exists(md_path), "FAIL: SUMMARY.md not found"
md = open(md_path).read()
for needle in ['epoch-5', 'regime', '−2.70',
               'fig1_test_accuracy_curves', 'fig2_accuracy_gap', 'fig3_loss_curves']:
    assert needle in md, f"FAIL: '{needle}' not found in SUMMARY.md"
print(f"\n✓ results/SUMMARY.md  — all required strings present")

# 4. Figures exist
for fig_name in ['fig1_test_accuracy_curves.png', 'fig1_test_accuracy_curves.pdf',
                 'fig2_accuracy_gap.png', 'fig2_accuracy_gap.pdf',
                 'fig3_loss_curves.png', 'fig3_loss_curves.pdf']:
    path = f'figures/{fig_name}'
    sz = os.path.getsize(path) / 1024
    print(f"  figures/{fig_name}  ({sz:.1f} KB)")

print("\n" + "=" * 65)
print("ALL CHECKS PASSED ✓")
print("=" * 65)
