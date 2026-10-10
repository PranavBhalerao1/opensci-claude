
# Fix: the regex was matching seed numbers (42, 123) too — use 3+ digit requirement
import re, os

summary_text = open("results/SUMMARY.md").read()

# Match rows where N is a training size (>=3 digits, so 500+ but not 42 or 123)
delta_table_rows = re.findall(r"^\| [\d,]{3,} \|", summary_text, re.MULTILINE)
print(f"Delta table rows (N>=100): {len(delta_table_rows)}")
print(delta_table_rows)

# Verify all 7 sizes appear
sizes_expected = [500, 1000, 2500, 5000, 10000, 30000, 60000]
for s in sizes_expected:
    pattern = f"| {s:,} |"
    assert pattern in summary_text, f"Missing size {s:,} in SUMMARY"
print("✓ All 7 training sizes present in SUMMARY.md")

# Verify regression equation
assert "-11.9996" in summary_text
assert "0.5305" in summary_text
print("✓ Regression equation values present")

# Verify N*
assert "6,448,676" in summary_text
print("✓ N* present")

# Verify GPU
assert "NVIDIA L4" in summary_text
print("✓ GPU info present")

# Check file size
fsize = os.path.getsize("results/SUMMARY.md")
assert fsize > 0
print(f"✓ results/SUMMARY.md  {fsize:,} bytes")

# Check latex
tex = open("paper/table_results.tex").read()
assert r"\begin{tabular}" in tex
assert r"\end{tabular}" in tex
data_rows_tex = re.findall(r"^\s+[\d,]+ &", tex, re.MULTILINE)
print(f"\n✓ paper/table_results.tex — tabular data rows: {len(data_rows_tex)}")
assert len(data_rows_tex) == 7

# Check bar chart
fsize_fig = os.path.getsize("figures/fig_test_acc_bars.png")
print(f"✓ figures/fig_test_acc_bars.png  {fsize_fig/1024:.1f} KB")
assert fsize_fig > 10_000

print("\n✅ ALL ACCEPTANCE CHECKS PASSED")
