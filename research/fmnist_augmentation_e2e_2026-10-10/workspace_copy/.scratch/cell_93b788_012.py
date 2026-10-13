
import subprocess, sys, os

# Quick smoke test: 2 epochs, CPU, check CSV format
result = subprocess.run(
    [sys.executable, 'src/train.py',
     '--seed', '42', '--augment', 'false', '--epochs', '2',
     '--data_dir', 'data/fashion_mnist', '--out_dir', '/tmp/smoke_fix'],
    capture_output=True, text=True, timeout=120
)
print("STDOUT (last 20 lines):")
print('\n'.join(result.stdout.split('\n')[-20:]))
if result.returncode != 0:
    print("STDERR:", result.stderr[-500:])
