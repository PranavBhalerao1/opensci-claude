
import sys, os
sys.path.insert(0, os.getcwd())

import random
import numpy as np
import torch
from src.model import set_seed, SmallCNN

print("[6] set_seed() coverage check")
set_seed(99)
r1 = random.random()
set_seed(99)
r2 = random.random()
ok_rand = r1 == r2

set_seed(99)
n1 = np.random.rand()
set_seed(99)
n2 = np.random.rand()
ok_numpy = n1 == n2

set_seed(99)
t1 = torch.rand(1).item()
set_seed(99)
t2 = torch.rand(1).item()
ok_torch = t1 == t2

print(f"  random reproducible  : {ok_rand}")
print(f"  numpy reproducible   : {ok_numpy}")
print(f"  torch reproducible   : {ok_torch}")
print(f"  cudnn deterministic  : {torch.backends.cudnn.deterministic}")
print(f"  cudnn benchmark off  : {not torch.backends.cudnn.benchmark}")

# Detailed SmallCNN architecture check
print("\n[7] SmallCNN architecture check")
model = SmallCNN()

# Verify conv blocks
def check_block(block, in_ch, out_ch, name):
    conv = block[0]
    bn   = block[1]
    relu = block[2]
    pool = block[3]
    ok = (
        isinstance(conv, torch.nn.Conv2d) and
        conv.in_channels == in_ch and
        conv.out_channels == out_ch and
        conv.kernel_size == (3, 3) and
        conv.padding == (1, 1) and
        isinstance(bn, torch.nn.BatchNorm2d) and
        isinstance(relu, torch.nn.ReLU) and
        isinstance(pool, torch.nn.MaxPool2d)
    )
    print(f"  {name}: in={in_ch}→out={out_ch}, 3×3, pad=1, BN+ReLU+MaxPool → {'OK' if ok else 'FAIL'}")
    return ok

ok_b1 = check_block(model.block1, 1, 32, "Block1")
ok_b2 = check_block(model.block2, 32, 64, "Block2")
ok_b3 = check_block(model.block3, 64, 128, "Block3")

# Check FC head
clf = model.classifier
ok_fc = (
    isinstance(clf[0], torch.nn.Flatten) and
    isinstance(clf[1], torch.nn.Linear) and clf[1].out_features == 256 and
    isinstance(clf[2], torch.nn.ReLU) and
    isinstance(clf[3], torch.nn.Dropout) and abs(clf[3].p - 0.5) < 1e-6 and
    isinstance(clf[4], torch.nn.Linear) and clf[4].out_features == 10
)
print(f"  FC head: Flatten→Linear(256)→ReLU→Dropout(0.5)→Linear(10) → {'OK' if ok_fc else 'FAIL'}")

# Forward pass check
x = torch.zeros(8, 1, 28, 28)
with torch.no_grad():
    y = model(x)
ok_shape = y.shape == (8, 10)
print(f"  Forward pass (8,1,28,28) → {tuple(y.shape)} → {'OK' if ok_shape else 'FAIL'}")

n_params = sum(p.numel() for p in model.parameters())
print(f"  Total parameters: {n_params:,}")

all_ok = ok_rand and ok_numpy and ok_torch and ok_b1 and ok_b2 and ok_b3 and ok_fc and ok_shape
print(f"\n  ALL ARCHITECTURE+SEED CHECKS: {'PASSED' if all_ok else 'FAILED'}")
