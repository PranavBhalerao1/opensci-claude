"""
train_fmnist.py
===============
Self-contained module for training SmallCNN on Fashion-MNIST subsets.

Exports
-------
SmallCNN            – two conv-block architecture with BN, Dropout, MaxPool
get_transforms      – transform factory for 'noaug' / 'aug' conditions
train_one_epoch     – single epoch training loop, returns mean loss
evaluate_accuracy   – evaluation loop, returns accuracy float
CLI                 – argparse entry point (--seed, --size, --condition, ...)

Provenance
----------
Architecture / hyperparameters from config/config.json (project spec, 2026-10-09).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from pathlib import Path
from typing import Literal

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class SmallCNN(nn.Module):
    """
    Small CNN for Fashion-MNIST (1×28×28 → 10 classes).

    Block 1 : Conv(1→32,3×3,p=1) → BN → ReLU → Conv(32→32,3×3,p=1) → BN → ReLU
              → MaxPool(2) → Dropout(0.25)
    Block 2 : Conv(32→64,3×3,p=1) → BN → ReLU → Conv(64→64,3×3,p=1) → BN → ReLU
              → MaxPool(2) → Dropout(0.25)
    Head    : Flatten → Linear(3136,256) → ReLU → Dropout(0.5) → Linear(256,10)
    """

    def __init__(
        self,
        conv_filters: list[int] | None = None,
        fc_units: int = 256,
        dropout_conv: float = 0.25,
        dropout_fc: float = 0.5,
        num_classes: int = 10,
    ) -> None:
        super().__init__()
        if conv_filters is None:
            conv_filters = [32, 32, 64, 64]
        assert len(conv_filters) == 4, "conv_filters must have exactly 4 entries"
        c1, c2, c3, c4 = conv_filters

        # --- Block 1 ---
        self.block1 = nn.Sequential(
            nn.Conv2d(1,  c1, kernel_size=3, padding=1),
            nn.BatchNorm2d(c1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c1, c2, kernel_size=3, padding=1),
            nn.BatchNorm2d(c2),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2),          # 28×28 → 14×14
            nn.Dropout2d(p=dropout_conv),
        )

        # --- Block 2 ---
        self.block2 = nn.Sequential(
            nn.Conv2d(c2, c3, kernel_size=3, padding=1),
            nn.BatchNorm2d(c3),
            nn.ReLU(inplace=True),
            nn.Conv2d(c3, c4, kernel_size=3, padding=1),
            nn.BatchNorm2d(c4),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2),          # 14×14 → 7×7
            nn.Dropout2d(p=dropout_conv),
        )

        # --- Head ---
        # After two MaxPool(2): 28 → 14 → 7  ⟹  c4 × 7 × 7 = 64×49 = 3136
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(c4 * 7 * 7, fc_units),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout_fc),
            nn.Linear(fc_units, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # (B,1,28,28) → (B,10)
        x = self.block1(x)
        x = self.block2(x)
        x = self.head(x)
        return x


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def get_transforms(
    condition: Literal["noaug", "aug"],
    mean: float = 0.2860,
    std: float = 0.3530,
) -> transforms.Compose:
    """
    Return a torchvision transform pipeline.

    Parameters
    ----------
    condition : 'noaug' | 'aug'
        'noaug' – ToTensor + Normalize only.
        'aug'   – RandomHorizontalFlip(p=0.5) + RandomAffine(degrees=10,
                  translate=(0.1, 0.1)) + ToTensor + Normalize.
    mean, std : normalization statistics for Fashion-MNIST greyscale channel.
    """
    normalize = transforms.Normalize(mean=[mean], std=[std])

    if condition == "noaug":
        return transforms.Compose([
            transforms.ToTensor(),
            normalize,
        ])
    elif condition == "aug":
        return transforms.Compose([
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomAffine(degrees=10, translate=(0.1, 0.1)),
            transforms.ToTensor(),
            normalize,
        ])
    else:
        raise ValueError(f"Unknown condition '{condition}'. Choose 'noaug' or 'aug'.")


# ---------------------------------------------------------------------------
# Training / evaluation utilities
# ---------------------------------------------------------------------------

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """
    Run one full training epoch.

    Returns
    -------
    float
        Mean training loss over all mini-batches.
    """
    model.train()
    total_loss = 0.0
    n_batches = 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def evaluate_accuracy(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> float:
    """
    Evaluate classification accuracy on a DataLoader.

    Returns
    -------
    float
        Top-1 accuracy in [0, 1].
    """
    model.eval()
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            logits = model(images)
            preds = logits.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)

    return correct / max(total, 1)


# ---------------------------------------------------------------------------
# Seed / reproducibility helper
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> None:
    """Fix random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Dataset / loader builder
# ---------------------------------------------------------------------------

def build_loaders(
    data_root: str,
    condition: str,
    indices_path: str | None,
    batch_size: int,
    num_workers: int = 2,
) -> tuple[DataLoader, DataLoader]:
    """
    Build train and validation DataLoaders.

    If *indices_path* is given the training split is restricted to those
    integer indices (a .npy file produced by the Data Engineer).
    The full 10 000-sample test split is always used for evaluation.
    """
    train_tf = get_transforms(condition)
    val_tf   = get_transforms("noaug")   # validation never augmented

    train_dataset = datasets.FashionMNIST(
        root=data_root, train=True, download=True, transform=train_tf
    )
    val_dataset = datasets.FashionMNIST(
        root=data_root, train=False, download=True, transform=val_tf
    )

    if indices_path is not None:
        indices = np.load(indices_path).tolist()
        train_dataset = Subset(train_dataset, indices)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=256,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True,
    )
    return train_loader, val_loader


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train SmallCNN on a Fashion-MNIST subset."
    )
    parser.add_argument("--seed",         type=int,   required=True,
                        help="Random seed (e.g. 42 or 123).")
    parser.add_argument("--size",         type=int,   required=True,
                        help="Training subset size.")
    parser.add_argument("--condition",    type=str,   required=True,
                        choices=["noaug", "aug"],
                        help="Augmentation condition.")
    parser.add_argument("--indices_path", type=str,   default=None,
                        help="Path to .npy file with training indices.")
    parser.add_argument("--output_csv",   type=str,   default="results.csv",
                        help="Destination CSV for per-epoch metrics.")
    parser.add_argument("--data_root",    type=str,   default="data/",
                        help="Root directory for Fashion-MNIST download.")
    parser.add_argument("--config",       type=str,   default="config/config.json",
                        help="Path to config JSON.")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)

    # --- load config ---
    cfg_path = Path(args.config)
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
    else:
        cfg = {}

    training_cfg = cfg.get("training", {})
    lr         = float(training_cfg.get("lr",         0.001))
    batch_size = int(  training_cfg.get("batch_size", 64))
    epochs     = int(  training_cfg.get("epochs",     5))

    arch_cfg = cfg.get("architecture", {})
    conv_filters  = arch_cfg.get("conv_filters",  [32, 32, 64, 64])
    fc_units      = int(arch_cfg.get("fc_units",  256))
    dropout_conv  = float(arch_cfg.get("dropout_conv", 0.25))
    dropout_fc    = float(arch_cfg.get("dropout_fc",   0.5))

    # --- setup ---
    set_seed(args.seed)
    device = (
        torch.device("cuda")  if torch.cuda.is_available() else
        torch.device("mps")   if torch.backends.mps.is_available() else
        torch.device("cpu")
    )
    print(f"[train_fmnist] device={device}  seed={args.seed}  "
          f"size={args.size}  condition={args.condition}")

    # --- data ---
    train_loader, val_loader = build_loaders(
        data_root    = args.data_root,
        condition    = args.condition,
        indices_path = args.indices_path,
        batch_size   = batch_size,
    )

    # --- model ---
    model = SmallCNN(
        conv_filters=conv_filters,
        fc_units=fc_units,
        dropout_conv=dropout_conv,
        dropout_fc=dropout_fc,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    # --- train ---
    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["seed", "size", "condition", "epoch", "train_loss", "val_accuracy"]

    with open(args.output_csv, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for epoch in range(1, epochs + 1):
            train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
            val_acc    = evaluate_accuracy(model, val_loader, device)

            print(f"  epoch {epoch}/{epochs}  "
                  f"loss={train_loss:.4f}  val_acc={val_acc:.4f}")

            writer.writerow({
                "seed":         args.seed,
                "size":         args.size,
                "condition":    args.condition,
                "epoch":        epoch,
                "train_loss":   round(train_loss, 6),
                "val_accuracy": round(val_acc,    6),
            })

    print(f"[train_fmnist] results saved → {args.output_csv}")


if __name__ == "__main__":
    main()
