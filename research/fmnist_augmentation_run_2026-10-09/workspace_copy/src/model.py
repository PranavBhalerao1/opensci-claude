"""
src/model.py
SmallCNN architecture for Fashion-MNIST classification.

Architecture:
  Conv block 1: 1  → 32  channels, 3×3 kernel, padding=1, BN, ReLU, MaxPool(2)
  Conv block 2: 32 → 64  channels, 3×3 kernel, padding=1, BN, ReLU, MaxPool(2)
  Conv block 3: 64 → 128 channels, 3×3 kernel, padding=1, BN, ReLU, MaxPool(2)
  FC head     : Flatten → 256 units (ReLU) → Dropout(0.5) → 10 classes

Input: (B, 1, 28, 28)  — grayscale Fashion-MNIST
Output: (B, 10)         — raw logits (use CrossEntropyLoss)

Author : A1 / T1.3
Date   : 2026-10-09
"""

import random
import numpy as np
import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# Reproducibility helper
# ---------------------------------------------------------------------------

def set_seed(seed: int = 42) -> None:
    """Set seeds for random, numpy, torch (CPU+GPU), and cudnn determinism."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)          # multi-GPU safety
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# Conv block helper
# ---------------------------------------------------------------------------

def _conv_block(in_channels: int, out_channels: int) -> nn.Sequential:
    """3×3 conv (padding=1) → BatchNorm → ReLU → MaxPool(2×2)."""
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels,
                  kernel_size=3, padding=1, bias=False),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(kernel_size=2, stride=2),
    )


# ---------------------------------------------------------------------------
# SmallCNN
# ---------------------------------------------------------------------------

class SmallCNN(nn.Module):
    """
    Three-block convolutional network for 10-class image classification.

    Parameters
    ----------
    num_classes : int
        Number of output classes (default 10 for Fashion-MNIST).
    dropout : float
        Dropout probability applied after the 256-unit FC layer (default 0.5).

    Shapes (Fashion-MNIST, input 1×28×28)
    ------
    After block 1 (1 →  32): 32×14×14
    After block 2 (32→  64): 64×7×7
    After block 3 (64→ 128): 128×3×3   (floor(7/2)=3)
    After flatten           : 128*3*3 = 1152
    FC hidden (256) + dropout + FC out (10)
    """

    def __init__(self, num_classes: int = 10, dropout: float = 0.5):
        super().__init__()

        # Three convolutional blocks: 1 → 32 → 64 → 128
        self.block1 = _conv_block(1, 32)
        self.block2 = _conv_block(32, 64)
        self.block3 = _conv_block(64, 128)

        # Compute flattened size dynamically (28×28 input)
        self._flat_size = 128 * 3 * 3   # = 1152

        # Fully-connected head
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(self._flat_size, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        return self.classifier(x)

    # ------------------------------------------------------------------
    # Convenience: compute flat size from an actual input (for safety)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_flat_size(in_channels: int = 1,
                          height: int = 28,
                          width: int = 28) -> int:
        """Dry-run a dummy batch to find the post-conv flat dimension."""
        dummy = torch.zeros(1, in_channels, height, width)
        model = SmallCNN.__new__(SmallCNN)
        model.block1 = _conv_block(1, 32)
        model.block2 = _conv_block(32, 64)
        model.block3 = _conv_block(64, 128)
        with torch.no_grad():
            out = model.block3(model.block2(model.block1(dummy)))
        return int(out.numel())


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    set_seed(42)
    model = SmallCNN()
    print(model)

    x = torch.randn(4, 1, 28, 28)
    with torch.no_grad():
        y = model(x)
    print(f"\nInput  shape : {tuple(x.shape)}")
    print(f"Output shape : {tuple(y.shape)}  (expected: (4, 10))")
    assert y.shape == (4, 10), f"Bad output shape: {y.shape}"

    # Parameter count
    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nTotal parameters     : {n_params:,}")
    print(f"Trainable parameters : {n_trainable:,}")
    print("\nSmallCNN self-test PASSED.")
