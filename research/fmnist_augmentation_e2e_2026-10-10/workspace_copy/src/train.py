#!/usr/bin/env python3
"""
train.py — Fashion-MNIST SmallCNN training script
==================================================
Study : Augmentation Benefit Direction in the 5-Epoch Underfitting Regime:
        A Crossover Analysis for Small CNNs on Fashion-MNIST
Spec  : docs/architecture_spec.md (version 1.0, 2026-10-10)
Author: ML Implementation Agent (T1.2) — accuracy-as-percentage fix (T2.1 v2)
Date  : 2026-10-10

Architecture  (NO BatchNorm anywhere)
--------------------------------------
  Block 1 : Conv2d(1→32, 3×3, pad=1) + ReLU + MaxPool2d(kernel=2, stride=2)
  Block 2 : Conv2d(32→64, 3×3, pad=1) + ReLU + MaxPool2d(kernel=2, stride=2)
  Flatten : 64 × 7 × 7 = 3 136
  FC1     : Linear(3136 → 256) + ReLU + Dropout(p=0.25)
  FC2     : Linear(256 → 10)   [raw logits; loss applied externally]

CSV format
----------
  Line 1  : # seed=<s> augment=<b> device=<d> start=<iso>,train_loss,...,test_acc
            ← comment+column headers on ONE LINE (first col name = # comment)
            ← ensures pd.read_csv(path) returns exactly `epochs` data rows
  Lines 2+: one row per epoch, accuracies stored as PERCENTAGES (×100)
             e.g. 88.23 not 0.8823

  NOTE: train_acc / val_acc / test_acc are stored as percentages in [0, 100].
  This means test_acc for a reasonable model should be in [50, 99].
  NOTE: column named "# seed=..." is the epoch number column (first col).
"""

import argparse
import csv
import os
import random
import sys
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as T
from torch.utils.data import DataLoader, Dataset, random_split


# ---------------------------------------------------------------------------
# 1.  Architecture
# ---------------------------------------------------------------------------

class SmallCNN(nn.Module):
    """
    Two Conv-ReLU-MaxPool blocks → Flatten → FC(3136→256)+ReLU+Dropout(0.25)
    → FC(256→10).  NO BatchNorm anywhere (deliberate design choice).
    Total trainable parameters: 824 458.
    """

    def __init__(self):
        super().__init__()
        # Block 1
        self.conv1 = nn.Conv2d(in_channels=1, out_channels=32,
                               kernel_size=3, padding=1)
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)

        # Block 2
        self.conv2 = nn.Conv2d(in_channels=32, out_channels=64,
                               kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)

        # FC layers
        self.fc1 = nn.Linear(64 * 7 * 7, 256)
        self.dropout = nn.Dropout(p=0.25)
        self.fc2 = nn.Linear(256, 10)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.pool1(self.relu(self.conv1(x)))
        x = self.pool2(self.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = self.dropout(self.relu(self.fc1(x)))
        return self.fc2(x)


# ---------------------------------------------------------------------------
# 2.  Augmentation-aware Subset wrapper
# ---------------------------------------------------------------------------

class TransformSubset(Dataset):
    def __init__(self, subset, transform):
        self.subset = subset
        self.transform = transform

    def __len__(self):
        return len(self.subset)

    def __getitem__(self, idx):
        img, label = self.subset[idx]
        if self.transform is not None:
            img = self.transform(img)
        return img, label


# ---------------------------------------------------------------------------
# 3.  Data-loading helpers
# ---------------------------------------------------------------------------

FMNIST_MEAN = (0.2860,)
FMNIST_STD  = (0.3530,)
TRAIN_SIZE  = 55_000
VAL_SIZE    = 5_000


def build_transforms(augment: bool):
    eval_tf = T.Compose([
        T.ToTensor(),
        T.Normalize(mean=FMNIST_MEAN, std=FMNIST_STD),
    ])
    if augment:
        train_tf = T.Compose([
            T.RandomHorizontalFlip(p=0.5),
            T.RandomCrop(28, padding=3),
            T.RandomRotation(degrees=10),
            T.ToTensor(),
            T.Normalize(mean=FMNIST_MEAN, std=FMNIST_STD),
        ])
    else:
        train_tf = eval_tf
    return train_tf, eval_tf


def load_datasets(data_dir: str, augment: bool, seed: int, batch_size: int = 64):
    base_train = torchvision.datasets.FashionMNIST(
        root=data_dir, train=True, download=True, transform=None)
    base_test = torchvision.datasets.FashionMNIST(
        root=data_dir, train=False, download=True, transform=None)

    generator = torch.Generator().manual_seed(seed)
    train_subset, val_subset = random_split(
        base_train, [TRAIN_SIZE, VAL_SIZE], generator=generator)

    train_tf, eval_tf = build_transforms(augment)
    train_ds = TransformSubset(train_subset, train_tf)
    val_ds   = TransformSubset(val_subset,   eval_tf)
    test_ds  = TransformSubset(base_test,    eval_tf)

    train_loader = DataLoader(train_ds, batch_size=batch_size,
                              shuffle=True,  num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_ds,   batch_size=256,
                              shuffle=False, num_workers=0, pin_memory=False)
    test_loader  = DataLoader(test_ds,  batch_size=256,
                              shuffle=False, num_workers=0, pin_memory=False)
    return train_loader, val_loader, test_loader


# ---------------------------------------------------------------------------
# 4.  Training / evaluation helpers
# ---------------------------------------------------------------------------

def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += images.size(0)
    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    correct = 0
    total = 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        preds = model(images).argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += images.size(0)
    return correct / total


# ---------------------------------------------------------------------------
# 5.  Seeding
# ---------------------------------------------------------------------------

def fix_seeds(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# 6.  Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Train SmallCNN on Fashion-MNIST")
    parser.add_argument("--seed",     type=int, default=42)
    parser.add_argument("--augment",  type=str, default="false",
                        choices=["true", "false"])
    parser.add_argument("--epochs",   type=int, default=30)
    parser.add_argument("--data_dir", type=str, default="data/fashion_mnist")
    parser.add_argument("--out_dir",  type=str, default="data")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 7.  Main
# ---------------------------------------------------------------------------

CHECKPOINT_EPOCHS = {5, 10, 20, 30}


def main():
    args    = parse_args()
    seed    = args.seed
    augment = args.augment.lower() == "true"
    epochs  = args.epochs
    aug_tag = "aug" if augment else "noaug"
    start_dt = datetime.now().isoformat(timespec="seconds")

    fix_seeds(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[{start_dt}] seed={seed} augment={augment} epochs={epochs} "
          f"device={device}", flush=True)

    ckpt_dir = os.path.join(args.out_dir, "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, f"metrics_seed{seed}_{aug_tag}.csv")

    train_loader, val_loader, test_loader = load_datasets(
        args.data_dir, augment, seed)

    model     = SmallCNN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"SmallCNN trainable parameters: {n_params:,}  (expected 824,458)",
          flush=True)
    assert n_params == 824_458, f"Parameter count mismatch: got {n_params}"

    # -----------------------------------------------------------------------
    # CSV setup — write comment header + column names, NO epoch-0 row
    # Accuracies stored as PERCENTAGES (multiply fraction by 100)
    # so that test_acc is in [0, 100] and typically [50, 99] for a trained model.
    # -----------------------------------------------------------------------
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        # Combine the # comment and column names into ONE header line so that
        # pd.read_csv(path) returns exactly `epochs` data rows (not epochs+1).
        # The first column name IS the comment (starts with "#", contains device).
        comment_col = (f"# seed={seed} augment={augment} "
                       f"device={device} start={start_dt}")
        writer.writerow([comment_col, "train_loss", "train_acc",
                         "val_acc", "test_acc"])

    # -----------------------------------------------------------------------
    # Training loop — epochs 1 .. epochs  (exactly `epochs` rows in CSV)
    # -----------------------------------------------------------------------
    for epoch in range(1, epochs + 1):
        train_loss, train_acc = train_one_epoch(
            model, train_loader, optimizer, criterion, device)
        val_acc  = evaluate(model, val_loader,  device)
        test_acc = evaluate(model, test_loader, device)

        # Store accuracies as percentages
        train_acc_pct = round(train_acc * 100, 4)
        val_acc_pct   = round(val_acc   * 100, 4)
        test_acc_pct  = round(test_acc  * 100, 4)

        print(f"Epoch {epoch:3d}/{epochs}  "
              f"train_loss={train_loss:.4f}  "
              f"train_acc={train_acc_pct:.2f}%  "
              f"val_acc={val_acc_pct:.2f}%  "
              f"test_acc={test_acc_pct:.2f}%",
              flush=True)

        with open(csv_path, "a", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([epoch,
                             round(train_loss,    6),
                             train_acc_pct,
                             val_acc_pct,
                             test_acc_pct])

        if epoch in CHECKPOINT_EPOCHS:
            ckpt_name = f"checkpoint_seed{seed}_{aug_tag}_ep{epoch}.pt"
            ckpt_path = os.path.join(ckpt_dir, ckpt_name)
            torch.save({
                "epoch":       epoch,
                "seed":        seed,
                "augment":     augment,
                "model_state": model.state_dict(),
                "optim_state": optimizer.state_dict(),
                "train_loss":  train_loss,
                "train_acc":   train_acc_pct,
                "val_acc":     val_acc_pct,
                "test_acc":    test_acc_pct,
            }, ckpt_path)
            print(f"  ✓ Checkpoint saved → {ckpt_path}", flush=True)

    print(f"\nDone.  CSV  → {csv_path}")
    print(f"        Ckpt → {ckpt_dir}/")
    print(f"FINAL: epoch-{epochs} test_acc={test_acc_pct:.2f}%", flush=True)


if __name__ == "__main__":
    main()
