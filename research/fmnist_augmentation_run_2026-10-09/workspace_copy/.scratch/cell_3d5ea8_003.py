
# ── 1. Dummy forward-pass validation ──────────────────────────────────────────
import sys
sys.path.insert(0, ".")

import torch
from src.model import SmallCNN, set_seed

set_seed(42)
model = SmallCNN(num_classes=10)
model.eval()

# Single sample
x1 = torch.randn(1, 1, 28, 28)
out1 = model(x1)
assert out1.shape == (1, 10), f"Bad shape: {out1.shape}"

# Batch of 32
x32 = torch.randn(32, 1, 28, 28)
out32 = model(x32)
assert out32.shape == (32, 10), f"Bad shape: {out32.shape}"

# Gradient flow check
model.train()
loss = torch.nn.CrossEntropyLoss()(out32, torch.randint(0, 10, (32,)))
loss.backward()
grad_ok = all(p.grad is not None for p in model.parameters() if p.requires_grad)
assert grad_ok, "Some parameters have no gradient!"

print("✓ Forward-pass shapes  : OK (batch-1 and batch-32)")
print("✓ Gradient flow        : OK")
print(f"  Input  shape : {x32.shape}")
print(f"  Output shape : {out32.shape}")

# Architecture summary
from torchinfo import summary
print()
summary(model, input_size=(1, 1, 28, 28), verbose=1,
        col_names=["input_size","output_size","num_params"])
