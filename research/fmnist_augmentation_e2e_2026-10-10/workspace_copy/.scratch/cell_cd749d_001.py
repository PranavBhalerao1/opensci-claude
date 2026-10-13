
import os, pathlib

csv_path = pathlib.Path("data/metrics_seed42_aug.csv")
print("File exists:", csv_path.exists())
if csv_path.exists():
    print("File size:", csv_path.stat().st_size, "bytes")
    with open(csv_path) as f:
        lines = f.readlines()
    print(f"Total lines in file: {len(lines)}")
    print("\n--- First 5 lines (raw) ---")
    for i, line in enumerate(lines[:5]):
        print(f"  [{i}]: {repr(line)}")
    print("\n--- Last 3 lines (raw) ---")
    for i, line in enumerate(lines[-3:]):
        print(f"  [{len(lines)-3+i}]: {repr(line)}")
