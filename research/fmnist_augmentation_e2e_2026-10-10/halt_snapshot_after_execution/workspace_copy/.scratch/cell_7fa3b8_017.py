
# Print final artifact summary
print("PRODUCED ARTIFACTS\n" + "─" * 55)
artifacts = [
    ('analysis/table1_checkpoint_summary.csv', 'Formatted checkpoint summary — 4 rows × 8 cols'),
    ('analysis/table1_checkpoint_summary.tex', 'LaTeX tabular with booktabs rules'),
    ('figures/fig2_accuracy_gap.png',          'Fig 2 gap trajectory (PNG, 300 dpi)'),
    ('figures/fig2_accuracy_gap.pdf',          'Fig 2 gap trajectory (PDF, 300 dpi)'),
    ('results/SUMMARY.md',                     'Final results summary for Report stage'),
]
for path, desc in artifacts:
    sz = os.path.getsize(path) / 1024
    print(f"  {path:<45} {sz:7.1f} KB  — {desc}")
