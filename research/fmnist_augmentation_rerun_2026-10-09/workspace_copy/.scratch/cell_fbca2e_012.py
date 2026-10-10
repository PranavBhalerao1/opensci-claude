
import re

# Extract device name strings from log files
device_lines = {}
for seed, logfile in [(42, 'results/gpu_log_seed42.txt'), (123, 'results/gpu_log_seed123.txt')]:
    with open(logfile, 'r') as f:
        content = f.read()
    # Find device line
    match = re.search(r'device:\s*(.+)', content)
    device_name = match.group(1).strip() if match else 'UNKNOWN'
    device_lines[seed] = device_name
    print(f"seed={seed}: device='{device_name}'")

# Write gpu_device_info.txt
gpu_device_info_content = f"""GPU Device Information
======================
Source: results/gpu_log_seed42.txt  (accessed 2026-10-09)
Source: results/gpu_log_seed123.txt (accessed 2026-10-09)

Seed 42  — Device: {device_lines[42]}
Seed 123 — Device: {device_lines[123]}

Full log contents:
------------------
[gpu_log_seed42.txt]
"""

with open('results/gpu_log_seed42.txt', 'r') as f:
    gpu_device_info_content += f.read()

gpu_device_info_content += "\n[gpu_log_seed123.txt]\n"

with open('results/gpu_log_seed123.txt', 'r') as f:
    gpu_device_info_content += f.read()

with open('analysis/gpu_device_info.txt', 'w') as f:
    f.write(gpu_device_info_content)

print("\n✓ Saved analysis/gpu_device_info.txt")
print(f"  File size: {len(gpu_device_info_content)} chars")

# Print the file content for verification
print("\n=== File contents ===")
print(gpu_device_info_content)
