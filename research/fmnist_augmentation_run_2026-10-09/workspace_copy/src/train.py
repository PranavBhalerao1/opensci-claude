"""
src/train.py
Training pipeline for SmallCNN on Fashion-MNIST.

Provides:
  train_epoch()    — one epoch of SGD/Adam over the training DataLoader
  evaluate()       — loss + accuracy on a DataLoader (no grad)
  run_training()   — full training loop with checkpoint recovery and CSV logging

Checkpoints are saved to  data/checkpoints/<run_name>_epoch<N>.pt
CSV logs are saved to      data/logs/<run_name>.csv
Best model is saved to     data/checkpoints/<run_name>_best.pt

GPU probe: at startup, probe_gpu() is called to update
           data/environment_report.txt with the actual device name
           (important when executing via run_gpu_jobs on a GPU node).

Author : A1 / T1.4
Date   : 2026-10-09
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from tqdm import tqdm

# Add project root to path so sibling imports work from any CWD
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.model import SmallCNN, set_seed  # noqa: E402


# ---------------------------------------------------------------------------
# GPU probe — updates data/environment_report.txt when training starts on GPU
# ---------------------------------------------------------------------------

def _update_env_report() -> Optional[str]:
    """
    If a CUDA GPU is available, regenerate data/environment_report.txt
    with the actual device name and memory.  Returns the device name
    string, or None if no GPU is present.

    This function is called once at the start of run_training() so that
    when A3 submits GPU jobs via run_gpu_jobs, the report file is updated
    before any analysis/verification occurs.
    """
    if not torch.cuda.is_available():
        return None

    probe_script = _ROOT / "scripts" / "probe_gpu.py"
    if probe_script.exists():
        import subprocess
        result = subprocess.run(
            [sys.executable, str(probe_script)],
            capture_output=True, text=True,
            cwd=str(_ROOT),
        )
        if result.returncode == 0:
            print("[train] environment_report.txt updated with GPU info.")
        else:
            print(f"[train] probe_gpu.py warning: {result.stderr[:200]}")

    # Return the primary device name
    return torch.cuda.get_device_properties(0).name


# ---------------------------------------------------------------------------
# Core training functions
# ---------------------------------------------------------------------------

def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    scaler: Optional[torch.cuda.amp.GradScaler] = None,
) -> tuple[float, float]:
    """
    Run one training epoch.

    Parameters
    ----------
    model     : network in train mode
    loader    : training DataLoader
    optimizer : e.g. SGD or Adam
    criterion : loss function (CrossEntropyLoss)
    device    : torch.device
    scaler    : optional AMP GradScaler for mixed-precision training

    Returns
    -------
    (avg_loss, accuracy)  — floats over the full epoch
    """
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)

        if scaler is not None:
            with torch.autocast(device_type=device.type, dtype=torch.float16):
                logits = model(images)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

        batch_size = labels.size(0)
        total_loss += loss.item() * batch_size
        preds = logits.argmax(dim=1)
        correct += preds.eq(labels).sum().item()
        total += batch_size

    avg_loss = total_loss / total
    accuracy = correct / total
    return avg_loss, accuracy


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float]:
    """
    Evaluate model on a DataLoader (no gradient).

    Returns
    -------
    (avg_loss, accuracy)
    """
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            logits = model(images)
            loss = criterion(logits, labels)

            batch_size = labels.size(0)
            total_loss += loss.item() * batch_size
            preds = logits.argmax(dim=1)
            correct += preds.eq(labels).sum().item()
            total += batch_size

    return total_loss / total, correct / total


# ---------------------------------------------------------------------------
# Full training loop
# ---------------------------------------------------------------------------

def run_training(
    run_name: str,
    train_loader: DataLoader,
    val_loader: DataLoader,
    num_epochs: int = 30,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    seed: int = 42,
    device_str: str = "cuda",
    use_amp: bool = True,
    checkpoint_dir: str = "data/checkpoints",
    log_dir: str = "data/logs",
    resume: bool = True,
) -> dict:
    """
    Train SmallCNN with epoch-level checkpointing and CSV logging.

    Parameters
    ----------
    run_name      : unique identifier, e.g. "noaug_seed42"
    train_loader  : DataLoader for training set
    val_loader    : DataLoader for validation / test set
    num_epochs    : total training epochs
    lr            : initial learning rate
    weight_decay  : L2 regularisation
    seed          : RNG seed (applied via set_seed)
    device_str    : "cuda" or "cpu"
    use_amp       : enable automatic mixed precision (CUDA only)
    checkpoint_dir: directory for .pt checkpoint files
    log_dir       : directory for CSV log files
    resume        : if True, try to resume from latest checkpoint

    Returns
    -------
    dict with keys: best_val_acc, final_val_acc, history (list of dicts)
    """
    # ------------------------------------------------------------------
    # 0. GPU probe — update environment_report.txt on first GPU run
    # ------------------------------------------------------------------
    gpu_name = _update_env_report()
    if gpu_name:
        print(f"[train] GPU: {gpu_name}")

    # ------------------------------------------------------------------
    # 1. Seed and device
    # ------------------------------------------------------------------
    set_seed(seed)
    device = torch.device(device_str if torch.cuda.is_available() else "cpu")
    print(f"[train] Device: {device}")

    # ------------------------------------------------------------------
    # 2. Model, loss, optimizer, scheduler
    # ------------------------------------------------------------------
    model = SmallCNN(num_classes=10, dropout=0.5).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        model.parameters(), lr=lr, weight_decay=weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=num_epochs, eta_min=1e-5
    )

    # AMP scaler (only on CUDA)
    use_amp = use_amp and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler() if use_amp else None

    # ------------------------------------------------------------------
    # 3. Directories
    # ------------------------------------------------------------------
    os.makedirs(checkpoint_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    ckpt_prefix = os.path.join(checkpoint_dir, run_name)
    log_path = os.path.join(log_dir, f"{run_name}.csv")
    best_path = f"{ckpt_prefix}_best.pt"

    # ------------------------------------------------------------------
    # 4. Resume from checkpoint (crash recovery)
    # ------------------------------------------------------------------
    start_epoch = 0
    best_val_acc = 0.0
    history: list[dict] = []

    if resume:
        # Find latest epoch checkpoint
        latest_epoch = -1
        for fname in os.listdir(checkpoint_dir):
            if fname.startswith(run_name + "_epoch") and fname.endswith(".pt"):
                try:
                    ep = int(fname.split("_epoch")[1].replace(".pt", ""))
                    if ep > latest_epoch:
                        latest_epoch = ep
                except ValueError:
                    pass

        if latest_epoch >= 0:
            ckpt_path = f"{ckpt_prefix}_epoch{latest_epoch}.pt"
            print(f"[train] Resuming from {ckpt_path}")
            ckpt = torch.load(ckpt_path, map_location=device)
            model.load_state_dict(ckpt["model_state"])
            optimizer.load_state_dict(ckpt["optimizer_state"])
            scheduler.load_state_dict(ckpt["scheduler_state"])
            start_epoch = ckpt["epoch"]          # next epoch to run
            best_val_acc = ckpt.get("best_val_acc", 0.0)
            history = ckpt.get("history", [])
            if scaler is not None and "scaler_state" in ckpt:
                scaler.load_state_dict(ckpt["scaler_state"])
            print(f"[train] Resumed at epoch {start_epoch}, best val acc: "
                  f"{best_val_acc:.4f}")

    # ------------------------------------------------------------------
    # 5. CSV log — write header if starting fresh
    # ------------------------------------------------------------------
    csv_fields = [
        "epoch", "train_loss", "train_acc", "val_loss", "val_acc",
        "lr", "epoch_time_s",
    ]
    write_header = (not resume) or (start_epoch == 0) or (not os.path.exists(log_path))
    csv_file = open(log_path, "a", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
    if write_header:
        writer.writeheader()

    # ------------------------------------------------------------------
    # 6. Training loop
    # ------------------------------------------------------------------
    print(f"[train] Starting run '{run_name}' — epochs {start_epoch+1}..{num_epochs}")
    try:
        for epoch in range(start_epoch, num_epochs):
            t0 = time.perf_counter()

            train_loss, train_acc = train_epoch(
                model, train_loader, optimizer, criterion, device, scaler
            )
            val_loss, val_acc = evaluate(model, val_loader, criterion, device)
            scheduler.step()

            elapsed = time.perf_counter() - t0
            current_lr = scheduler.get_last_lr()[0]

            row = {
                "epoch": epoch + 1,
                "train_loss": round(train_loss, 6),
                "train_acc": round(train_acc, 6),
                "val_loss": round(val_loss, 6),
                "val_acc": round(val_acc, 6),
                "lr": round(current_lr, 8),
                "epoch_time_s": round(elapsed, 2),
            }
            history.append(row)
            writer.writerow(row)
            csv_file.flush()

            # Console output
            print(
                f"  Epoch {epoch+1:3d}/{num_epochs} | "
                f"train loss {train_loss:.4f} acc {train_acc:.4f} | "
                f"val loss {val_loss:.4f} acc {val_acc:.4f} | "
                f"{elapsed:.1f}s"
            )

            # Save best model
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                torch.save(
                    {
                        "epoch": epoch + 1,
                        "model_state": model.state_dict(),
                        "val_acc": val_acc,
                        "run_name": run_name,
                    },
                    best_path,
                )

            # Epoch checkpoint (for crash recovery)
            epoch_ckpt = f"{ckpt_prefix}_epoch{epoch+1}.pt"
            torch.save(
                {
                    "epoch": epoch + 1,
                    "model_state": model.state_dict(),
                    "optimizer_state": optimizer.state_dict(),
                    "scheduler_state": scheduler.state_dict(),
                    "scaler_state": scaler.state_dict() if scaler else {},
                    "best_val_acc": best_val_acc,
                    "history": history,
                    "run_name": run_name,
                    "seed": seed,
                },
                epoch_ckpt,
            )

            # Remove previous epoch checkpoint to save disk space
            # (keep last 2 to survive a crash mid-save)
            if epoch >= 2:
                old_ckpt = f"{ckpt_prefix}_epoch{epoch-1}.pt"
                if os.path.exists(old_ckpt):
                    os.remove(old_ckpt)

    finally:
        csv_file.close()

    print(f"[train] Run '{run_name}' complete. Best val acc: {best_val_acc:.4f}")
    return {
        "best_val_acc": best_val_acc,
        "final_val_acc": history[-1]["val_acc"] if history else 0.0,
        "history": history,
        "run_name": run_name,
        "device": str(device),
        "best_model_path": best_path,
    }


# ---------------------------------------------------------------------------
# Quick smoke test (run as main)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import torch.utils.data as data_utils

    print("=" * 60)
    print("src/train.py — smoke test (1 epoch, random data)")
    print("=" * 60)

    set_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Tiny random dataset (100 samples, 1×28×28, 10 classes)
    X = torch.randn(100, 1, 28, 28)
    y = torch.randint(0, 10, (100,))
    ds = data_utils.TensorDataset(X, y)
    loader = data_utils.DataLoader(ds, batch_size=16, shuffle=True)

    results = run_training(
        run_name="smoke_test",
        train_loader=loader,
        val_loader=loader,
        num_epochs=1,
        seed=42,
        device_str=str(device),
        use_amp=(device.type == "cuda"),
        checkpoint_dir="data/checkpoints",
        log_dir="data/logs",
        resume=False,
    )
    print("\nSmoke test results:", results)
    print("\nsrc/train.py smoke test PASSED.")
