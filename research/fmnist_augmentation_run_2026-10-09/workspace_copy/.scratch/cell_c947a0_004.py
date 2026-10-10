
import ctypes, ctypes.util

# Try using torch's bundled CUDA runtime
import os, torch
torch_dir = os.path.dirname(torch.__file__)
lib_path = os.path.join(torch_dir, 'lib', 'libtorch_cuda.so')

try:
    cuda = ctypes.CDLL(lib_path)
    
    # Try cudaGetDeviceCount
    count = ctypes.c_int(0)
    ret = cuda.cudaGetDeviceCount(ctypes.byref(count))
    print(f"cudaGetDeviceCount ret={ret}, count={count.value}")
    
    if count.value > 0:
        # Try cudaGetDeviceProperties
        # struct cudaDeviceProp has name as first 256 bytes
        class DeviceProp(ctypes.Structure):
            _fields_ = [("name", ctypes.c_char * 256),
                       ("padding", ctypes.c_char * 4096)]  # rest of struct
        
        prop = DeviceProp()
        ret2 = cuda.cudaGetDeviceProperties(ctypes.byref(prop), 0)
        print(f"cudaGetDeviceProperties ret={ret2}")
        print(f"Device name: {prop.name.decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")

# Also try the libcudart from torch
cudart_path = None
for root, dirs, files in os.walk(torch_dir):
    for f in files:
        if f.startswith('libcudart') and f.endswith('.so'):
            cudart_path = os.path.join(root, f)
            break

print(f"cudart path: {cudart_path}")
if cudart_path:
    try:
        cudart = ctypes.CDLL(cudart_path)
        count = ctypes.c_int(0)
        ret = cudart.cudaGetDeviceCount(ctypes.byref(count))
        print(f"cudaGetDeviceCount via cudart ret={ret}, count={count.value}")
    except Exception as e:
        print(f"cudart error: {e}")
