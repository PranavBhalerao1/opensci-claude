
import sys, platform, datetime, torch, torchvision, sklearn, matplotlib
import seaborn, pandas, numpy, scipy, tabulate, torchinfo, tqdm

ts       = datetime.datetime.utcnow().isoformat() + "Z"
py_ver   = sys.version.replace("\n", " ")
plat     = platform.platform()
torch_v  = torch.__version__
cuda_v   = torch.version.cuda          # "13.0" – torch built with CUDA
dev_cnt  = torch.cuda.device_count()   # 0 in this CPU-only agent shell
gpu_name = torch.cuda.get_device_name(0) if dev_cnt > 0 else "No GPU hardware detected (run_gpu_jobs target)"
mem_gb   = (torch.cuda.get_device_properties(0).total_memory / 1024**3
            if dev_cnt > 0 else float("nan"))

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

lines = [
    f"=== Environment Report ===",
    f"Timestamp (UTC)    : {ts}",
    f"",
    f"--- GPU / CUDA ---",
    f"CUDA built version : {cuda_v}   (torch.version.cuda)",
    f"GPU device count   : {dev_cnt}",
    f"GPU device name    : {gpu_name}",
    f"GPU total VRAM (GB): {mem_gb:.2f}" if dev_cnt > 0 else f"GPU total VRAM (GB): N/A",
    f"torch.cuda.is_available(): {torch.cuda.is_available()}",
    f"Note               : This agent shell is CPU-only; GPU training executes via",
    f"                     run_gpu_jobs (A3). CUDA 13.0 toolkit linked in torch build.",
    f"",
    f"--- Python / Platform ---",
    f"Python version     : {py_ver}",
    f"Platform           : {plat}",
    f"",
    f"--- PyTorch ---",
    f"PyTorch version    : {torch_v}",
    f"",
    f"--- Package Versions ---",
]
for pkg, ver in pkg_versions.items():
    lines.append(f"  {pkg:<14}: {ver}")

lines += [
    f"",
    f"--- Workspace Directories ---",
    f"  src/  data/  data/checkpoints/  data/logs/  data/predictions/",
    f"  analysis/  figures/  tables/  results/  scripts/",
    f"  (all created successfully)",
]

report = "\n".join(lines)
print(report)

with open("data/environment_report.txt", "w") as f:
    f.write(report + "\n")
print("\n✓ Written data/environment_report.txt")
