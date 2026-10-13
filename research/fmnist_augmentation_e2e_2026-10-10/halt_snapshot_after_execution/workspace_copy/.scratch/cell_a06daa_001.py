
import os, glob

# Check what's available
print("=== analysis/ directory ===")
for f in sorted(os.listdir("analysis")):
    size = os.path.getsize(f"analysis/{f}")
    print(f"  {f}  ({size} bytes)")

print("\n=== scripts/ directory ===")
for f in sorted(os.listdir("scripts")):
    print(f"  {f}")

print("\n=== results/ (if exists) ===")
if os.path.isdir("results"):
    for f in sorted(os.listdir("results")):
        print(f"  {f}")
