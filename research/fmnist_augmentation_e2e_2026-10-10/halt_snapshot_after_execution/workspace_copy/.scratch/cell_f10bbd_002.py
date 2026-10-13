
# Read the full train.py to inspect checkpoint naming and CSV format
with open("src/train.py") as f:
    content = f.read()

# Find the checkpoint saving section
idx = content.find("checkpoint")
print("=== Checkpoint-related lines ===")
for i, line in enumerate(content.splitlines()):
    if "checkpoint" in line.lower() or "ep" in line.lower() or "csv" in line.lower() or "metrics" in line.lower():
        print(f"{i+1:4d}: {line}")
