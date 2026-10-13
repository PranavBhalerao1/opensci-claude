import re

path = "docs/architecture_spec.md"

with open(path) as f:
    text = f.read()

# --- acceptance checks ---
assert len(text) > 0, "File is empty!"

# Check total parameter count
assert "824 458" in text or "824458" in text, "Total param count not found!"

# Check no BatchNorm
assert "No BatchNorm" in text or "no BatchNorm" in text or "None" in text, \
    "BatchNorm mention missing!"
assert "BatchNorm" in text and "None" in text, "BatchNorm=None not documented!"

# Check dropout=0.25 in FC only
assert "0.25" in text, "Dropout 0.25 not found!"
assert "FC" in text and "Dropout" in text, "FC+Dropout not documented!"

print("=== All acceptance checks PASSED ===\n")

# --- programmatic parameter count verification ---
conv1  = 1 * 32 * 3 * 3 + 32
conv2  = 32 * 64 * 3 * 3 + 64
fc1    = 3136 * 256 + 256
fc2    = 256 * 10 + 10
total  = conv1 + conv2 + fc1 + fc2

print(f"Conv1  : {conv1:>10,}")
print(f"Conv2  : {conv2:>10,}")
print(f"FC1    : {fc1:>10,}")
print(f"FC2    : {fc2:>10,}")
print(f"TOTAL  : {total:>10,}")
assert total == 824_458, f"Expected 824458, got {total}"
print("\nParameter count verified: 824,458 ✓")

# --- quick size sanity ---
print(f"\nFile size: {len(text)} chars, {text.count(chr(10))} lines")
