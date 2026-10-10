
# Try pynvml and GPUtil
try:
    import pynvml
    pynvml.nvmlInit()
    count = pynvml.nvmlDeviceGetCount()
    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        print(f"GPU {i}: {name}, Memory: {mem.total / 1024**3:.1f} GB")
except Exception as e:
    print(f"pynvml failed: {e}")

try:
    import GPUtil
    gpus = GPUtil.getGPUs()
    for gpu in gpus:
        print(f"GPUtil: {gpu.name}, {gpu.memoryTotal} MB")
    if not gpus:
        print("GPUtil: no GPUs found")
except Exception as e:
    print(f"GPUtil failed: {e}")
