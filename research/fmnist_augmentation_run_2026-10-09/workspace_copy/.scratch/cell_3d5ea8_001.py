
import sys, platform, datetime, torch, torchvision, sklearn, matplotlib, seaborn, pandas, numpy, scipy, tabulate, torchinfo, tqdm

# ── GPU assertion ──────────────────────────────────────────────────────────────
if not torch.cuda.is_available():
    raise RuntimeError("CUDA GPU is NOT available – aborting T1.1")

device      = torch.cuda.current_device()
dev_name    = torch.cuda.get_device_name(device)
total_mem   = torch.cuda.get_device_properties(device).total_memory / (1024**3)
cuda_ver    = torch.version.cuda
torch_ver   = torch.__version__
python_ver  = sys.version
py_platform = platform.platform()

print(f"GPU device  : {dev_name}")
print(f"Total VRAM  : {total_mem:.2f} GB")
print(f"PyTorch ver : {torch_ver}")
print(f"CUDA version: {cuda_ver}")
print(f"Python ver  : {python_ver}")
print(f"Platform    : {py_platform}")

# ── Package versions ──────────────────────────────────────────────────────────
pkg_versions = {
    "torch"       : torch.__version__,
    "torchvision" : torchvision.__version__,
    "scikit-learn": sklearn.__version__,
    "matplotlib"  : matplotlib.__version__,
    "seaborn"     : seaborn.__version__,
    "pandas"      : pandas.__version__,
    "numpy"       : numpy.__version__,
    "scipy"       : scipy.__version__,
    "tabulate"    : tabulate.__version__,
    "torchinfo"   : torchinfo.__version__,
    "tqdm"        : tqdm.__version__,
}
for k, v in pkg_versions.items():
    print(f"  {k:<14}: {v}")
