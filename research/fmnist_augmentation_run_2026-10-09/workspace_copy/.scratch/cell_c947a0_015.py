
import os, sys, subprocess, torch

print("=" * 65)
print("FINAL COMPREHENSIVE ACCEPTANCE CHECK")
print("=" * 65)

all_ok = True

# 1. Required directories
print("\n[1] Required directories")
required_dirs = ['src', 'data', 'data/checkpoints', 'data/logs',
                 'data/predictions', 'analysis', 'figures', 'tables',
                 'results', 'scripts']
for d in required_dirs:
    ok = os.path.isdir(d)
    status = "OK" if ok else "MISSING"
    print(f"  {d}/  {status}")
    if not ok:
        all_ok = False

# 2. environment_report.txt
print("\n[2] data/environment_report.txt")
rep_path = 'data/environment_report.txt'
ok_exists = os.path.exists(rep_path)
print(f"  Exists: {ok_exists}")

with open(rep_path) as f:
    rep_content = f.read()
    
ok_cuda = 'cuda' in rep_content.lower()
# Check for GPU device name (NVIDIA or known GPU model patterns)
import re
gpu_name_patterns = ['NVIDIA', 'GeForce', 'Quadro', 'Tesla', 'A100', 'V100', 'T4', 'RTX']
ok_gpu_name = any(p in rep_content for p in gpu_name_patterns)

print(f"  Contains 'cuda' (case-insensitive): {ok_cuda}")
print(f"  Contains GPU device name (NVIDIA/etc): {ok_gpu_name}")

# Show GPU Device Name line
for line in rep_content.split('\n'):
    if 'GPU Device Name' in line:
        print(f"  → {line.strip()}")

if not (ok_exists and ok_cuda and ok_gpu_name):
    all_ok = False

# 3. src/model.py
print("\n[3] src/model.py — SmallCNN architecture")
r = subprocess.run([sys.executable, 'src/model.py'], capture_output=True, text=True)
ok_model = r.returncode == 0 and 'PASSED' in r.stdout
print(f"  Self-test: {'PASSED' if ok_model else 'FAILED'}")
if not ok_model:
    print("  stderr:", r.stderr[:200])
    all_ok = False

# 4. src/train.py
print("\n[4] src/train.py — train_epoch / evaluate / run_training")
r = subprocess.run([sys.executable, 'src/train.py'], capture_output=True, text=True)
ok_train = r.returncode == 0 and 'PASSED' in r.stdout
print(f"  Smoke test: {'PASSED' if ok_train else 'FAILED'}")
if not ok_train:
    print("  stderr:", r.stderr[:200])
    all_ok = False

# 5. Package versions
print("\n[5] Package version check")
pkgs = {
    'torch': torch.__version__,
}
import torchvision, sklearn, matplotlib, numpy as np, scipy, seaborn, pandas, tabulate, tqdm, torchinfo
pkgs.update({
    'torchvision': torchvision.__version__,
    'sklearn': sklearn.__version__,
    'matplotlib': matplotlib.__version__,
    'numpy': np.__version__,
    'scipy': scipy.__version__,
    'seaborn': seaborn.__version__,
    'pandas': pandas.__version__,
    'tabulate': tabulate.__version__,
    'tqdm': tqdm.__version__,
    'torchinfo': torchinfo.__version__,
})
for pkg, ver in pkgs.items():
    print(f"  {pkg:15s}: {ver}")

# 6. set_seed coverage
print("\n[6] set_seed() coverage check")
from src.model import set_seed
import random, numpy as np2
set_seed(99)
r1 = random.random()
set_seed(99)
r2 = random.random()
ok_rand = r1 == r2
set_seed(99)
n1 = np2.random.rand()
set_seed(99)
n2 = np2.random.rand()
ok_numpy = n1 == n2
set_seed(99)
t1 = torch.rand(1).item()
set_seed(99)
t2 = torch.rand(1).item()
ok_torch = t1 == t2
print(f"  random reproducible:  {ok_rand}")
print(f"  numpy reproducible:   {ok_numpy}")
print(f"  torch reproducible:   {ok_torch}")
print(f"  cudnn deterministic:  {torch.backends.cudnn.deterministic}")
if not (ok_rand and ok_numpy and ok_torch):
    all_ok = False

print("\n" + "=" * 65)
print(f"OVERALL: {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
print("=" * 65)
