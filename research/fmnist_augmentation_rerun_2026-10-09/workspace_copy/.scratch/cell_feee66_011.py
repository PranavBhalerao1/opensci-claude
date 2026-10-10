
# Re-read current SUMMARY and patch the baseline accuracy table seed rows 
# to use "Seed 42" / "Seed 123" labels for clarity
content = open("results/SUMMARY.md").read()

# The current lines are like: "| 42  | ... |" and "| 123 | ... |"
# Replace them with "| Seed 42  |" and "| Seed 123 |"
import re
content2 = re.sub(r"\| 42  \|", "| Seed 42  |", content)
content2 = re.sub(r"\| 123 \|", "| Seed 123 |", content2)
# Also fix the header of that table
content2 = re.sub(r"\| Seed \| noaug acc", "| Seed | noaug acc", content2)

with open("results/SUMMARY.md", "w") as f:
    f.write(content2)

# Now re-verify
summary_text2 = open("results/SUMMARY.md").read()
delta_rows = re.findall(r"^\| [\d,]{3,} \|", summary_text2, re.MULTILINE)
print(f"Delta table rows (>=3 digit N): {delta_rows}")
# Check all 7 training sizes
sizes_expected = [500, 1000, 2500, 5000, 10000, 30000, 60000]
for s in sizes_expected:
    assert f"| {s:,} |" in summary_text2, f"Missing {s:,}"
print("✓ All 7 training sizes present")

# No seed numbers triggering false positives
assert "| 123 |" not in summary_text2
assert "| 42  |" not in summary_text2
print("✓ No ambiguous seed-number rows")

# All other checks
assert "-11.9996" in summary_text2
assert "0.5305" in summary_text2
assert "6,448,676" in summary_text2
assert "NVIDIA L4" in summary_text2
assert os.path.getsize("results/SUMMARY.md") > 0
print("✓ All content checks pass")
print(f"\nFinal SUMMARY.md size: {os.path.getsize('results/SUMMARY.md'):,} bytes")
