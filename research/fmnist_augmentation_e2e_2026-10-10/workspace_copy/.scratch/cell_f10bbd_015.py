
# Final artifact inventory
import os, pathlib

print("FINAL ARTIFACT INVENTORY")
print("=" * 60)

artifacts = []

# CSVs
for f in sorted(pathlib.Path("data").glob("metrics_*.csv")):
    size = f.stat().st_size
    artifacts.append(str(f))
    print(f"  CSV: {f}  ({size:,} bytes)")

print()

# Checkpoints
ckpts = sorted(pathlib.Path("data/checkpoints").glob("*.pt"))
print(f"  Checkpoints: {len(ckpts)} files")
for f in ckpts:
    size_mb = f.stat().st_size / 1e6
    artifacts.append(str(f))
    print(f"    {f.name}  ({size_mb:.1f} MB)")

print()
print(f"Total artifacts: {len(artifacts)}")
print(f"  CSVs: 4, Checkpoints: {len(ckpts)}")
