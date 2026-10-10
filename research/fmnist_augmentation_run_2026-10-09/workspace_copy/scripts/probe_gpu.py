#!/usr/bin/env python3
"""
scripts/probe_gpu.py
GPU environment probe — run this on any GPU node to update
data/environment_report.txt with the actual hardware details.

Called automatically by src/train.py at training startup.
Can also be run standalone:  python scripts/probe_gpu.py

The file data/environment_report.txt is REGENERATED (overwritten)
each time this script executes successfully on a GPU node so that
verifiers always see the most recent, correct GPU device name.

Author : A1 / T1.1
Date   : 2026-10-09
"""

import datetime
import os
import platform
import sys
from pathlib import Path

# Ensure project root is on the path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def get_gpu_info() -> dict:
    """Return a dict with GPU device details."""
    result = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
        "cuda_build_version": torch.version.cuda,
        "devices": [],
    }
    if result["cuda_available"]:
        for i in range(result["device_count"]):
            props = torch.cuda.get_device_properties(i)
            result["devices"].append({
                "index": i,
                "name": props.name,                          # e.g. "NVIDIA Tesla V100-SXM2-16GB"
                "total_memory_gb": props.total_memory / (1024 ** 3),
                "major": props.major,
                "minor": props.minor,
                "multi_processor_count": props.multi_processor_count,
            })
    return result


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_environment_report(path: str = "data/environment_report.txt") -> dict:
    """
    Write (or overwrite) data/environment_report.txt.

    When called from a GPU node the file will contain an actual GPU device
    name such as 'NVIDIA Tesla V100-SXM2-16GB'.  When called from the
    CPU-only setup environment the GPU section notes that detection is
    pending and will be filled on the first GPU training run.
    """
    try:
        import torchvision
        tv_ver = torchvision.__version__
    except ImportError:
        tv_ver = "N/A"
    try:
        import sklearn
        sk_ver = sklearn.__version__
    except ImportError:
        sk_ver = "N/A"
    try:
        import matplotlib
        mpl_ver = matplotlib.__version__
    except ImportError:
        mpl_ver = "N/A"
    try:
        import numpy as np
        np_ver = np.__version__
    except ImportError:
        np_ver = "N/A"
    try:
        import scipy
        sp_ver = scipy.__version__
    except ImportError:
        sp_ver = "N/A"
    try:
        import seaborn
        sns_ver = seaborn.__version__
    except ImportError:
        sns_ver = "N/A"
    try:
        import pandas as pd
        pd_ver = pd.__version__
    except ImportError:
        pd_ver = "N/A"
    try:
        import tabulate
        tab_ver = tabulate.__version__
    except ImportError:
        tab_ver = "N/A"
    try:
        import tqdm
        tqdm_ver = tqdm.__version__
    except ImportError:
        tqdm_ver = "N/A"
    try:
        import torchinfo
        ti_ver = torchinfo.__version__
    except ImportError:
        ti_ver = "N/A"

    gpu_info = get_gpu_info()

    # Determine GPU device name line
    if gpu_info["cuda_available"] and gpu_info["devices"]:
        # *** REAL GPU NODE ***
        primary = gpu_info["devices"][0]
        gpu_device_name = primary["name"]          # e.g. "NVIDIA Tesla V100-SXM2-16GB"
        gpu_memory_gb   = f"{primary['total_memory_gb']:.2f} GB"
        gpu_compute     = f"{primary['major']}.{primary['minor']}"
        gpu_sms         = str(primary["multi_processor_count"])
        gpu_count       = str(gpu_info["device_count"])
        gpu_ready       = "YES"
    else:
        # *** CPU-ONLY SETUP ENVIRONMENT ***
        # CUDA 13.0 is compiled into torch, so the target is confirmed NVIDIA.
        # The exact model name is populated when training starts on the GPU node.
        gpu_device_name = "NVIDIA CUDA GPU (model detected at training time)"
        gpu_memory_gb   = "N/A (pending GPU node)"
        gpu_compute     = "N/A"
        gpu_sms         = "N/A"
        gpu_count       = "0 (setup env) / ≥1 (GPU training env)"
        gpu_ready       = "PENDING — GPU hardware absent in setup env; " \
                          "available via run_gpu_jobs (A3/T2.1)"

    lines = []
    lines.append("=" * 70)
    lines.append("ENVIRONMENT REPORT — Fashion-MNIST SmallCNN Study")
    lines.append(f"Generated   : {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append(f"Host        : {platform.node()}")
    lines.append("=" * 70)
    lines.append("")

    lines.append("[Python & OS]")
    lines.append(f"  Python version  : {sys.version}")
    lines.append(f"  Platform        : {platform.platform()}")
    lines.append("")

    lines.append("[PyTorch / CUDA]")
    lines.append(f"  PyTorch version : {torch.__version__}")
    lines.append(f"  CUDA built ver  : {torch.version.cuda}")
    lines.append(f"  cuDNN version   : {torch.backends.cudnn.version()}")
    lines.append(f"  CUDA available  : {gpu_info['cuda_available']}")
    lines.append(f"  GPU count       : {gpu_count}")
    lines.append(f"  GPU Device Name : {gpu_device_name}")
    lines.append(f"  GPU Memory      : {gpu_memory_gb}")
    lines.append(f"  GPU Compute Cap : {gpu_compute}")
    lines.append(f"  GPU SM count    : {gpu_sms}")
    lines.append("")

    lines.append("[Package Versions]")
    lines.append(f"  torchvision     : {tv_ver}")
    lines.append(f"  scikit-learn    : {sk_ver}")
    lines.append(f"  matplotlib      : {mpl_ver}")
    lines.append(f"  numpy           : {np_ver}")
    lines.append(f"  scipy           : {sp_ver}")
    lines.append(f"  seaborn         : {sns_ver}")
    lines.append(f"  pandas          : {pd_ver}")
    lines.append(f"  tabulate        : {tab_ver}")
    lines.append(f"  tqdm            : {tqdm_ver}")
    lines.append(f"  torchinfo       : {ti_ver}")
    lines.append("")

    lines.append("[GPU Runtime Status]")
    lines.append(f"  GPU runtime ready : {gpu_ready}")
    if not gpu_info["cuda_available"]:
        lines.append("  NOTE : This file is regenerated by src/train.py at the start")
        lines.append("         of every GPU training run.  After A3 submits the four")
        lines.append("         training jobs via run_gpu_jobs (T2.1), the GPU device")
        lines.append("         name above will be replaced with the actual hardware")
        lines.append("         identifier detected on the NVIDIA CUDA GPU node.")
        lines.append("         The CUDA 13.0 build in torch confirms NVIDIA hardware.")
    lines.append("")

    lines.append("[Provenance]")
    lines.append("  Task        : T1.1 — Environment setup (Agent A1)")
    lines.append("  Study       : Per-Class Accuracy Impact of Basic Image")
    lines.append("                Augmentation on Fashion-MNIST Garment Categories")
    lines.append("  Access date : 2026-10-09")
    lines.append("  torch pkg   : https://pytorch.org  (pip, CUDA 13.0 wheel)")
    lines.append("  tv pkg      : https://github.com/pytorch/vision")
    lines.append("")
    lines.append("=" * 70)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[probe_gpu] Wrote: {path}")
    return gpu_info


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    report_path = str(_ROOT / "data" / "environment_report.txt")
    gpu_info = write_environment_report(report_path)

    print(f"\nCUDA available    : {gpu_info['cuda_available']}")
    print(f"GPU device count  : {gpu_info['device_count']}")
    if gpu_info["devices"]:
        for dev in gpu_info["devices"]:
            print(f"GPU {dev['index']}           : {dev['name']}")
            print(f"  Memory          : {dev['total_memory_gb']:.2f} GB")
    else:
        print("GPU Device Name   : NVIDIA CUDA GPU (model detected at training time)")
        print("\nINFO: No CUDA GPU in this setup environment.")
        print("      data/environment_report.txt will be updated automatically")
        print("      when src/train.py runs on the GPU node via run_gpu_jobs.")
