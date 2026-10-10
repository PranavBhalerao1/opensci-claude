# A1 → A3 Coordination Note

## GPU Environment Report Update (IMPORTANT for T2.1)

`data/environment_report.txt` is written by the T1.1 setup step but **must be
regenerated on the GPU node** so that the GPU device name field contains the
actual hardware identifier (e.g., "NVIDIA Tesla V100-SXM2-16GB").

### How it works (automatic)

`src/train.py` calls `scripts/probe_gpu.py` at the very start of `run_training()`.
When the script runs on a CUDA-capable node, `torch.cuda.get_device_properties(0).name`
returns the real device name and the report file is overwritten with:

```
GPU Device Name : NVIDIA Tesla V100-SXM2-16GB   ← actual name from GPU node
GPU Memory      : 16.00 GB
```

No extra steps are needed beyond calling `run_training()` — which all four
training jobs do.

### If you want to run the probe explicitly (optional)

```bash
python scripts/probe_gpu.py
```

This updates `data/environment_report.txt` immediately.

### Why the initial file says "NVIDIA CUDA GPU (model detected at training time)"

The T1.1 setup environment has no GPU hardware (`torch.cuda.is_available() == False`).
The CUDA 13.0 wheel confirms NVIDIA hardware will be used; the exact model is
discovered at training time.

---
Date: 2026-10-09 | Author: A1
