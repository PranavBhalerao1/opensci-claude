
import re

# Parse crossover report for the crossover epoch
with open('analysis/crossover_report.txt', 'r') as f:
    report_text = f.read()

# Look for crossover epoch value
crossover_epoch = None
# Search for "crossover_epoch" or "CROSSOVER EPOCH" in the report
for line in report_text.splitlines():
    line_lower = line.lower()
    # check for "no crossover"
    if 'no crossover' in line_lower and 'within 30' in line_lower:
        crossover_epoch = None
        print(f"Found: NO crossover — line: {line.strip()}")
        break
    # check for crossover_epoch = N
    m = re.search(r'crossover[_\s]epoch\s*[:=]\s*(\d+)', line, re.IGNORECASE)
    if m:
        crossover_epoch = int(m.group(1))
        print(f"Found crossover epoch = {crossover_epoch} — line: {line.strip()}")
        break

print(f"\nFinal crossover_epoch = {crossover_epoch}")
