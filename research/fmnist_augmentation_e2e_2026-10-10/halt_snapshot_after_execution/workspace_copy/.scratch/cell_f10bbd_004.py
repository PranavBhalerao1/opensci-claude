
# Patch train.py: change zero-padded epoch format to unpadded
# ep{epoch:02d} → ep{epoch}  (gives ep5, ep10, ep20, ep30 matching required outputs)

with open("src/train.py") as f:
    content = f.read()

original = '                         f"_ep{epoch:02d}.pt")'
patched  = '                         f"_ep{epoch}.pt")'

assert original in content, "Pattern not found – check indentation"
new_content = content.replace(original, patched, 1)

assert '                         f"_ep{epoch}.pt")' in new_content
assert '                         f"_ep{epoch:02d}.pt")' not in new_content

with open("src/train.py", "w") as f:
    f.write(new_content)

# Verify the patch
lines = new_content.splitlines()
for i, line in enumerate(lines):
    if "ep{epoch" in line or "ckpt_name" in line:
        print(f"{i+1:4d}: {line}")

print("\n✓ Patch applied: checkpoint epoch format changed to unpadded (ep5, ep10, ep20, ep30)")
