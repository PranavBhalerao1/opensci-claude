
import subprocess, sys, os

# Check all possible GPU detection methods
print("=== System Info ===")
result = subprocess.run(['cat', '/proc/driver/nvidia/version'], capture_output=True, text=True)
print("nvidia driver:", result.stdout[:200] if result.returncode==0 else "not found")

# Check CUDA via ctypes
import ctypes
libs_to_try = ['libcuda.so', 'libcuda.so.1', 'libcudart.so', 'libcudart.so.13',
               '/usr/local/cuda/lib64/libcuda.so', '/usr/local/cuda/lib64/libcudart.so']
for lib in libs_to_try:
    try:
        cuda = ctypes.CDLL(lib)
        print(f"Loaded: {lib}")
    except:
        pass

# Check torch CUDA internals
import torch
print(f"\ntorch.__version__: {torch.__version__}")
print(f"torch.version.cuda: {torch.version.cuda}")
print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
print(f"torch.cuda.device_count(): {torch.cuda.device_count()}")

# Try to init CUDA anyway
try:
    torch.cuda.init()
    print("CUDA init succeeded")
    print("Device count after init:", torch.cuda.device_count())
except Exception as e:
    print(f"CUDA init failed: {e}")
