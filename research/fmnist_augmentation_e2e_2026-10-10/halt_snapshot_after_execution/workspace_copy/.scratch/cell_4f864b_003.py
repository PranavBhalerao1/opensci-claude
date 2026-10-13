import sys
sys.path.insert(0, ".")

# ── 4. Architecture checks ───────────────────────────────────────────────────
import torch
from src.train import SmallCNN

model = SmallCNN()

# Parameter count
n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Total trainable params : {n_params:,}  (expect 824,458)")
assert n_params == 824_458

# No BatchNorm
import torch.nn as nn
bn_layers = [m for m in model.modules() if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d))]
print(f"BatchNorm layers : {len(bn_layers)}  (expect 0)")
assert len(bn_layers) == 0

# Two Conv blocks
conv_layers = [m for m in model.modules() if isinstance(m, nn.Conv2d)]
print(f"Conv2d layers : {len(conv_layers)}  (expect 2)")
assert len(conv_layers) == 2
assert conv_layers[0].in_channels == 1 and conv_layers[0].out_channels == 32
assert conv_layers[1].in_channels == 32 and conv_layers[1].out_channels == 64

# Two FC layers
fc_layers = [m for m in model.modules() if isinstance(m, nn.Linear)]
print(f"Linear layers : {len(fc_layers)}  (expect 2)")
assert len(fc_layers) == 2
assert fc_layers[0].in_features == 3136 and fc_layers[0].out_features == 256
assert fc_layers[1].in_features == 256  and fc_layers[1].out_features == 10

# Dropout(0.25)
drop_layers = [m for m in model.modules() if isinstance(m, nn.Dropout)]
print(f"Dropout layers : {len(drop_layers)}  (expect 1, p=0.25)")
assert len(drop_layers) == 1
assert drop_layers[0].p == 0.25

# Forward pass shape
model.eval()
x = torch.randn(4, 1, 28, 28)
out = model(x)
print(f"Forward pass output shape : {tuple(out.shape)}  (expect (4, 10))")
assert out.shape == (4, 10)

print("\n✓ All architecture checks passed")
