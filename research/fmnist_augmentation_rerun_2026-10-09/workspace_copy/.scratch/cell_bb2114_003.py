
# ── 3. Verify GPU log ──────────────────────────────────────────────────────
with open('results/gpu_log_seed42.txt') as f:
    log_content = f.read()
print("=== gpu_log_seed42.txt ===")
print(log_content)

# Check it's non-empty and contains a device name
assert len(log_content.strip()) > 0, "GPU log is empty"
assert "device:" in log_content, "No 'device:' line in GPU log"
device_line = [l for l in log_content.splitlines() if l.startswith("device:")][0]
device_name = device_line.replace("device:", "").strip()
assert len(device_name) > 0, "Device name is empty"
print(f"\n✓ GPU log contains device name: '{device_name}'")
print("✓ All acceptance checks PASSED")
