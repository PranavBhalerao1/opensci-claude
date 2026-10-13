
import os, pathlib

# Check required inputs
checks = [
    "src/train.py",
    "data/gpu_and_data_validation.txt",
]
for p in checks:
    exists = os.path.exists(p)
    size = os.path.getsize(p) if exists else 0
    print(f"{'✓' if exists else '✗'} {p}  ({size:,} bytes)")

# Also list any existing data/ files
print("\n--- data/ top-level ---")
for f in sorted(pathlib.Path("data").rglob("*"))[:30]:
    if f.is_file():
        print(f"  {f}  ({f.stat().st_size:,} bytes)")
