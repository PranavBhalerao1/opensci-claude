
import os, glob

# First, let's see what files exist
for f in sorted(glob.glob("data/metrics_*.csv")):
    print(f"=== {f} ===")
    with open(f) as fh:
        lines = fh.readlines()
    print(f"  Total lines: {len(lines)}")
    print(f"  Line 1: {lines[0].strip()}")
    print(f"  Line 2: {lines[1].strip()}")
    print(f"  Line 3: {lines[2].strip()}")
    print(f"  Last line: {lines[-1].strip()}")
    print()
