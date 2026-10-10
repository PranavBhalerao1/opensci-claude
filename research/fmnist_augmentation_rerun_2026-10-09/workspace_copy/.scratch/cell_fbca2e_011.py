
# ── Step 6: Extract GPU device names from log files ──────────────────────────
import re

gpu_info = {}
for seed, logfile in [(42, 'results/gpu_log_seed42.txt'), (123, 'results/gpu_log_seed123.txt')]:
    with open(logfile, 'r') as f:
        content = f.read()
    # Print first 500 chars to see structure
    print(f"=== gpu_log_seed{seed}.txt (first 500 chars) ===")
    print(content[:500])
    print()
    gpu_info[seed] = content
