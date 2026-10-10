
import os, re
summary_text2 = open("results/SUMMARY.md").read()
assert "-11.9996" in summary_text2
assert "0.5305" in summary_text2
assert "6,448,676" in summary_text2
assert "NVIDIA L4" in summary_text2
assert os.path.getsize("results/SUMMARY.md") > 0
print("✓ Content checks pass")

# Final artifact sizes
print(f"\n{'File':<45} {'Size':>10}")
print("-"*57)
for path in ["figures/fig_test_acc_bars.png", "paper/table_results.tex", "results/SUMMARY.md"]:
    sz = os.path.getsize(path)
    print(f"{path:<45} {sz:>10,} bytes")

# Spot-check first few lines of SUMMARY
print("\n--- SUMMARY.md (first 30 lines) ---")
for i, line in enumerate(summary_text2.split("\n")[:30], 1):
    print(f"{i:2}: {line}")
