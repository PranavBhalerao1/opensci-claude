
import os, pathlib

# First peek at the raw file to understand its structure
csv_path = pathlib.Path("data/metrics_seed123_aug.csv")
if csv_path.exists():
    with open(csv_path) as f:
        lines = f.readlines()
    print(f"Total lines in file: {len(lines)}")
    print("=== First 5 lines ===")
    for i, l in enumerate(lines[:5]):
        print(f"  [{i}] {repr(l)}")
    print("=== Last 3 lines ===")
    for i, l in enumerate(lines[-3:]):
        print(f"  [{len(lines)-3+i}] {repr(l)}")
else:
    print("FILE NOT FOUND:", csv_path.resolve())
    # List what's in data/
    for p in sorted(pathlib.Path("data").rglob("*")):
        print(p)
