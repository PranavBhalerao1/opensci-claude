import re

src = open("src/train.py").read()

# Find ALL lines containing "BatchNorm"
for i, line in enumerate(src.split("\n"), 1):
    if "BatchNorm" in line:
        print(f"  Line {i:3d}: {line.rstrip()}")

# Check specifically for nn.BatchNorm (actual usage)
nn_bn = re.findall(r'nn\.BatchNorm\w*', src)
print(f"\nActual nn.BatchNorm calls: {nn_bn}  (must be empty)")
assert len(nn_bn) == 0, "Found real BatchNorm usage!"
print("Confirmed: no actual BatchNorm in code ✓")
