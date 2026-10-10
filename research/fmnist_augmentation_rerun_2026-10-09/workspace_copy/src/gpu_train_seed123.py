"""
gpu_train_seed123.py
====================
Self-contained GPU training script for seed=123.

Trains SmallCNN on Fashion-MNIST for all 14 configurations:
  - sizes:      [500, 1000, 2500, 5000, 10000, 30000, 60000]
  - conditions: ['noaug', 'aug']

Saves per-epoch metrics to results/results_seed123.csv incrementally.
Writes CUDA device name to results/gpu_log_seed123.txt.

Mirrors src/gpu_train_seed42.py exactly but with seed=123.
Provenance: part of augmentation-vs-size study, 2026-10-09.
"""

import subprocess, sys

# ── 0.  Ensure dependencies ────────────────────────────────────────────────
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "torch", "torchvision", "numpy", "pandas"
])

# ── 1.  Imports ────────────────────────────────────────────────────────────
import csv
import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

# Make sure src/ is on the path regardless of cwd
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from train_fmnist import (
    SmallCNN,
    get_transforms,
    train_one_epoch,
    evaluate_accuracy,
)

# ── 2.  Config ─────────────────────────────────────────────────────────────
CONFIG_PATH      = REPO_ROOT / "config" / "config.json"
INDICES_PATH     = REPO_ROOT / "data"   / "subset_indices.npz"
DATA_ROOT        = str(REPO_ROOT / "data")
RESULTS_DIR      = REPO_ROOT / "results"
OUTPUT_CSV       = RESULTS_DIR / "results_seed123.csv"
GPU_LOG          = RESULTS_DIR / "gpu_log_seed123.txt"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

SEED       = 123
SIZES      = cfg["sizes"]          # [500, 1000, 2500, 5000, 10000, 30000, 60000]
CONDITIONS = ["noaug", "aug"]
EPOCHS     = cfg["training"]["epochs"]      # 5
LR         = cfg["training"]["lr"]          # 0.001
BATCH      = cfg["training"]["batch_size"]  # 64
MEAN       = cfg["normalization"]["mean"]
STD        = cfg["normalization"]["std"]

# ── 3.  Device ─────────────────────────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if torch.cuda.is_available():
    device_name = torch.cuda.get_device_name(0)
else:
    device_name = "CPU (no CUDA)"
print(f"Using device: {device_name}", flush=True)

with open(GPU_LOG, "w") as f:
    f.write(f"device: {device_name}\n")
    f.write(f"seed: {SEED}\n")
    f.write(f"torch version: {torch.__version__}\n")

# ── 4.  Load indices ───────────────────────────────────────────────────────
indices_npz = np.load(str(INDICES_PATH))

# ── 5.  Prepare test loader (full 10 000-sample test split, never augmented)
val_tf = get_transforms("noaug", mean=MEAN, std=STD)
full_test_dataset = datasets.FashionMNIST(
    root=DATA_ROOT, train=False, download=True, transform=val_tf
)
test_loader = DataLoader(
    full_test_dataset,
    batch_size=256,
    shuffle=False,
    num_workers=2,
    pin_memory=True,
)

# ── 6.  Full training dataset (used as base for Subset) ───────────────────
# We build them lazily inside the loop.

# ── 7.  CSV setup (write header only if file does not exist) ──────────────
COLUMNS = ["seed", "size", "condition", "epoch", "train_loss", "val_acc", "test_acc"]

if not OUTPUT_CSV.exists():
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()

# ── 8.  Training loop ──────────────────────────────────────────────────────
total_runs = len(SIZES) * len(CONDITIONS)
run_num = 0

for size in SIZES:
    for condition in CONDITIONS:
        run_num += 1
        print(f"\n[{run_num}/{total_runs}] seed={SEED}  size={size}  condition={condition}", flush=True)

        # Reproducibility
        random.seed(SEED)
        np.random.seed(SEED)
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)

        # Build train DataLoader from stratified indices
        train_key = f"train_{size}_{SEED}"
        val_key   = f"val_{size}_{SEED}"
        train_indices = indices_npz[train_key].tolist()
        val_indices   = indices_npz[val_key].tolist()

        train_tf = get_transforms(condition, mean=MEAN, std=STD)
        base_train_dataset = datasets.FashionMNIST(
            root=DATA_ROOT, train=True, download=False, transform=train_tf
        )
        base_val_dataset = datasets.FashionMNIST(
            root=DATA_ROOT, train=True, download=False, transform=val_tf
        )

        train_subset = Subset(base_train_dataset, train_indices)
        val_subset   = Subset(base_val_dataset,   val_indices)

        train_loader = DataLoader(
            train_subset,
            batch_size=BATCH,
            shuffle=True,
            num_workers=2,
            pin_memory=True,
        )
        val_loader_subset = DataLoader(
            val_subset,
            batch_size=256,
            shuffle=False,
            num_workers=2,
            pin_memory=True,
        )

        # Model + optimizer + criterion
        model = SmallCNN(
            conv_filters=cfg["architecture"]["conv_filters"],
            fc_units=cfg["architecture"]["fc_units"],
            dropout_conv=cfg["architecture"]["dropout_conv"],
            dropout_fc=cfg["architecture"]["dropout_fc"],
        ).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        criterion = nn.CrossEntropyLoss()

        # Epoch loop
        for epoch in range(1, EPOCHS + 1):
            train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
            val_acc    = evaluate_accuracy(model, val_loader_subset, device)

            # Test accuracy only at final epoch
            if epoch == EPOCHS:
                test_acc = evaluate_accuracy(model, test_loader, device)
            else:
                test_acc = float("nan")

            row = {
                "seed":       SEED,
                "size":       size,
                "condition":  condition,
                "epoch":      epoch,
                "train_loss": round(train_loss, 6),
                "val_acc":    round(val_acc, 6),
                "test_acc":   round(test_acc, 6) if not math.isnan(test_acc) else "",
            }
            # Append row to CSV incrementally
            with open(OUTPUT_CSV, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writerow(row)

            print(
                f"  epoch {epoch}/{EPOCHS}  "
                f"loss={train_loss:.4f}  val_acc={val_acc:.4f}"
                + (f"  test_acc={test_acc:.4f}" if epoch == EPOCHS else ""),
                flush=True,
            )

# ── 9.  Final summary ──────────────────────────────────────────────────────
df = pd.read_csv(OUTPUT_CSV)
print(f"\n=== DONE: results_seed123.csv has {len(df)} rows (expected 70) ===", flush=True)
print(df.head())
print("...")
print(df.tail())

# Append summary to gpu_log
with open(GPU_LOG, "a") as f:
    f.write(f"\ntotal rows in CSV: {len(df)}\n")
    f.write(f"sizes present: {sorted(df['size'].unique().tolist())}\n")
    f.write(f"conditions present: {sorted(df['condition'].unique().tolist())}\n")
    f.write(f"seeds present: {sorted(df['seed'].unique().tolist())}\n")
    f.write("STATUS: COMPLETE\n")

print(f"\ngpu_log written to {GPU_LOG}", flush=True)
