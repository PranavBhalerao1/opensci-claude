
# Read the full train.py
with open("src/train.py") as f:
    content = f.read()

# Show the exact checkpoint naming line and surrounding context
lines = content.splitlines()
for i, line in enumerate(lines):
    if "ep{epoch" in line or "ckpt_name" in line:
        for j in range(max(0,i-2), min(len(lines), i+4)):
            print(f"{j+1:4d}: {lines[j]}")
        print("---")
