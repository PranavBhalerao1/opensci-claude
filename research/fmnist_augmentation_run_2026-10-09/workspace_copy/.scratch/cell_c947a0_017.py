
import os

# Verify environment_report.txt
with open('data/environment_report.txt') as f:
    content = f.read()

print("=== data/environment_report.txt ===")
print(content)

# Final acceptance check summary
print("=== ACCEPTANCE CHECK ===")
has_cuda = 'cuda' in content.lower()
has_gpu_name = 'NVIDIA' in content  # GPU Device Name line contains "NVIDIA CUDA GPU"
print(f"1. File exists:                    {os.path.exists('data/environment_report.txt')}")
print(f"2. Contains 'cuda' (case-insens):  {has_cuda}")
print(f"3. Contains GPU device name (NVIDIA): {has_gpu_name}")

# Show exact GPU Device Name line
for line in content.split('\n'):
    if 'GPU Device Name' in line:
        print(f"   Line: '{line.strip()}'")

# Directory check
print("\n=== REQUIRED DIRECTORIES ===")
dirs = ['src', 'data', 'data/checkpoints', 'data/logs', 'data/predictions',
        'analysis', 'figures', 'tables', 'results', 'scripts']
for d in dirs:
    print(f"  {d}/  {'✓' if os.path.isdir(d) else '✗ MISSING'}")

# List key files
print("\n=== KEY FILES ===")
for f in ['src/model.py', 'src/train.py', 'src/__init__.py',
          'scripts/probe_gpu.py', 'data/environment_report.txt']:
    exists = os.path.exists(f)
    size = os.path.getsize(f) if exists else 0
    print(f"  {f}  {'✓' if exists else '✗'} ({size:,} bytes)")
