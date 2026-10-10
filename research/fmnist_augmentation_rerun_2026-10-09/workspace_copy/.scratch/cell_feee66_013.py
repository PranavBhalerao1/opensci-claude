
# Print the rest of SUMMARY.md to confirm completeness
lines = open("results/SUMMARY.md").read().split("\n")
for i, line in enumerate(lines[30:], 31):
    print(f"{i:2}: {line}")
