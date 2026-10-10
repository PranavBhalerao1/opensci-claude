
import subprocess, sys, os

# Try subprocess to get GPU info in a fresh Python process
# Sometimes a subprocess has different env/access
result = subprocess.run(
    [sys.executable, '-c', 
     '''
import torch
print("cuda_available:", torch.cuda.is_available())
print("device_count:", torch.cuda.device_count())
import os
# Try setting CUDA_VISIBLE_DEVICES
os.environ.pop("CUDA_VISIBLE_DEVICES", None)
print("after pop cuda_available:", torch.cuda.is_available())
'''],
    capture_output=True, text=True, timeout=30
)
print(result.stdout)
print(result.stderr[:300] if result.stderr else "")

# Check CUDA_VISIBLE_DEVICES env var
print("CUDA_VISIBLE_DEVICES:", os.environ.get('CUDA_VISIBLE_DEVICES', 'not set'))
print("CUDA_DEVICE_ORDER:", os.environ.get('CUDA_DEVICE_ORDER', 'not set'))
