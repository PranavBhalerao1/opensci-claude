
with open("src/train.py") as f:
    content = f.read()

# Find the CSV header comment logic
lines = content.splitlines()
for i, line in enumerate(lines):
    if "comment" in line.lower() or "header" in line.lower() or "device_name" in line.lower() or "device" in line.lower():
        if "cuda" in line.lower() or "device" in line.lower() or "#" in line:
            print(f"{i+1:4d}: {line}")
