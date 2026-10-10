
import ctypes, struct, os, subprocess

# Try nvidia-ml-py
try:
    import nvidia_ml_py as nvml
    nvml.nvmlInit()
    count = nvml.nvmlDeviceGetCount()
    print(f"nvidia_ml_py: {count} devices")
    for i in range(count):
        h = nvml.nvmlDeviceGetHandleByIndex(i)
        print(nvml.nvmlDeviceGetName(h))
except Exception as e:
    print(f"nvidia_ml_py: {e}")

# Check LD_LIBRARY_PATH 
print("\nLD_LIBRARY_PATH:", os.environ.get('LD_LIBRARY_PATH', 'not set'))

# Try to find CUDA libs in torch package itself
import torch
torch_dir = os.path.dirname(torch.__file__)
cuda_libs = []
for root, dirs, files in os.walk(torch_dir):
    for f in files:
        if 'cuda' in f.lower() and f.endswith('.so'):
            cuda_libs.append(os.path.join(root, f))
print(f"\nFound {len(cuda_libs)} CUDA .so files in torch dir")
if cuda_libs:
    print("First few:", cuda_libs[:3])
    
# Try loading cuda from torch's own libs
for lib in cuda_libs[:5]:
    try:
        loaded = ctypes.CDLL(lib)
        if hasattr(loaded, 'cudaGetDeviceCount'):
            print(f"Has cudaGetDeviceCount: {lib}")
    except:
        pass
