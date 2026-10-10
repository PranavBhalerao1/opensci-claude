
import os, re

print("=" * 60)
print("FINAL ACCEPTANCE CHECKS — T4.3")
print("=" * 60)

# 1. figures/fig_test_acc_bars.png exists and > 10 KB
fsize = os.path.getsize("figures/fig_test_acc_bars.png")
assert fsize > 10_000, f"Too small: {fsize}"
print(f"✓ figures/fig_test_acc_bars.png  {fsize/1024:.1f} KB  (>10 KB)")

# 2. paper/table_results.tex: tabular env + exactly 7 data rows
tex = open("paper/table_results.tex").read()
assert r"\begin{tabular}" in tex
assert r"\end{tabular}" in tex
data_rows = re.findall(r"^\s+[\d,]+ &", tex, re.MULTILINE)
assert len(data_rows) == 7, f"Expected 7 data rows, got {len(data_rows)}"
print(f"✓ paper/table_results.tex  tabular env present, {len(data_rows)} data rows")

# 3. results/SUMMARY.md non-empty, has regression equation with values
md = open("results/SUMMARY.md").read()
assert len(md) > 0
assert "-11.9996" in md, "intercept missing"
assert "0.5305" in md, "slope missing"
assert "6,448,676" in md, "N* missing"
print(f"✓ results/SUMMARY.md  non-empty ({len(md):,} chars), regression equation present, N* present")

# 4. Δ table has all 7 training sizes
for s in [500, 1000, 2500, 5000, 10000, 30000, 60000]:
    assert f"| {s:,} |" in md, f"Missing size {s}"
print("✓ results/SUMMARY.md  Δ table contains all 7 training sizes")

# 5. GPU device info from gpu_device_info.txt
assert "NVIDIA L4" in md
print("✓ results/SUMMARY.md  GPU device name (NVIDIA L4) present")

print("\n✅ ALL 5 ACCEPTANCE CHECKS PASSED")
