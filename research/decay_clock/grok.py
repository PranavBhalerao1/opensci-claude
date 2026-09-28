"""Grokking under weight-decay schedules: lean, standard setup (Nanda et al. 2023).

One-layer transformer (d=128, 4 heads, MLP 512, no LayerNorm), modular arithmetic
p=97 with a fixed 30% train split, full-batch AdamW (betas 0.9/0.98). Weight decay
and learning rate follow a per-step schedule; decoupled AdamW decay shrinks every
parameter by (1 - eta_t*lambda_t) per step, so the cumulative log-shrinkage is
B(t) = sum_u -log(1 - eta_u*lambda_u).

Usage: python grok.py RUN_ID TASK CONDITION SEED T OUTDIR
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

# Setting overrides for generality experiments (defaults = main study).
P = int(os.environ.get("GROK_P", 97))
TRAIN_FRAC = float(os.environ.get("GROK_FRAC", 0.3))
SPLIT_SEED = int(os.environ.get("GROK_SPLIT", 598))
LAYERS = int(os.environ.get("GROK_LAYERS", 1))
D, H, DM = 128, 4, 512
EVAL_EVERY = 100
BASE_ETA = 1e-3


def schedule(cond: str, T: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-step (eta, lambda). All decaying conditions except the magnitude sweep have
    the same total shrinkage as constant lambda=1 over T."""
    t = np.arange(T)
    eta = np.full(T, BASE_ETA)
    if cond.startswith("const"):
        lam = np.full(T, float(cond[5:]))
    elif cond == "early":
        lam = np.where(t < T // 2, 2.0, 0.0)
    elif cond == "late":
        lam = np.where(t < T // 2, 0.0, 2.0)
    elif cond == "ramp":
        lam = 2.0 * t / (T - 1)
    elif cond == "lr2":  # same per-step shrinkage eta*lambda as const1, different learning rate
        eta = np.full(T, 2 * BASE_ETA)
        lam = np.full(T, 0.5)
    elif cond == "lrhalf":  # same per-step shrinkage as const1 with half the learning rate
        eta = np.full(T, BASE_ETA / 2)
        lam = np.full(T, 2.0)
    elif cond == "nowd":
        lam = np.zeros(T)
    else:
        raise ValueError(cond)
    return eta, lam


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.qkv = nn.Linear(D, 3 * D, bias=False)
        self.out = nn.Linear(D, D, bias=False)
        self.mlp_in = nn.Linear(D, DM)
        self.mlp_out = nn.Linear(DM, D)
        self.register_buffer("mask", torch.tril(torch.ones(3, 3, dtype=torch.bool)))

    def forward(self, h):
        n = h.shape[0]
        q, k, v = self.qkv(h).view(n, 3, 3, H, D // H).permute(2, 0, 3, 1, 4)
        att = (q @ k.transpose(-1, -2)) / math.sqrt(D // H)
        att = att.masked_fill(~self.mask, float("-inf")).softmax(-1)
        h = h + self.out((att @ v).transpose(1, 2).reshape(n, 3, D))
        return h + self.mlp_out(torch.relu(self.mlp_in(h)))


class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(P + 1, D)
        self.pos = nn.Parameter(torch.randn(3, D) / math.sqrt(D))
        self.blocks = nn.ModuleList(Block() for _ in range(LAYERS))
        self.unembed = nn.Linear(D, P, bias=False)

    def forward(self, x):
        h = self.embed(x) + self.pos
        for block in self.blocks:
            h = block(h)
        return self.unembed(h[:, -1])


def data(task: str, device):
    a, b = np.meshgrid(np.arange(P), np.arange(P), indexing="ij")
    a, b = a.ravel(), b.ravel()
    y = (a + b) % P if task == "add" else (a - b) % P
    x = np.stack([a, b, np.full_like(a, P)], 1)
    perm = np.random.default_rng(SPLIT_SEED).permutation(len(y))
    n_train = int(TRAIN_FRAC * len(y))
    tr, te = perm[:n_train], perm[n_train:]
    t = lambda arr: torch.tensor(arr, device=device)  # noqa: E731
    return t(x[tr]), t(y[tr]), t(x[te]), t(y[te])


def first_persistent(steps, acc, thr=0.99, k=3):
    """First eval step at which acc >= thr for k consecutive evaluations."""
    run = 0
    for i, a in enumerate(acc):
        run = run + 1 if a >= thr else 0
        if run == k:
            return int(steps[i - k + 1])
    return None


def main():
    run_id, task, cond, seed, T, outdir = sys.argv[1:7]
    seed, T = int(seed), int(T)
    out = Path(outdir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.backends.cuda.matmul.allow_tf32 = True
    xtr, ytr, xte, yte = data(task, dev)
    torch.manual_seed(seed)
    model = Model().to(dev)
    eta, lam = schedule(cond, T)
    opt = torch.optim.AdamW(model.parameters(), lr=float(eta[0]), betas=(0.9, 0.98), weight_decay=float(lam[0]))
    b = -np.log1p(-eta * lam)
    B = np.concatenate([[0.0], np.cumsum(b)])
    lossf = nn.CrossEntropyLoss()
    log = {k: [] for k in ("step", "B", "train_acc", "test_acc", "train_loss", "test_loss", "norm")}
    start = time.time()

    def evaluate(step):
        with torch.no_grad():
            ltr = model(xtr)
            lte = model(xte)
            log["step"].append(step)
            log["B"].append(float(B[step]))
            log["train_acc"].append(float((ltr.argmax(-1) == ytr).float().mean()))
            log["test_acc"].append(float((lte.argmax(-1) == yte).float().mean()))
            log["train_loss"].append(float(lossf(ltr, ytr)))
            log["test_loss"].append(float(lossf(lte, yte)))
            log["norm"].append(float(torch.sqrt(sum((p.float() ** 2).sum() for p in model.parameters()))))

    for step in range(T):
        if step % EVAL_EVERY == 0:
            evaluate(step)
        for g in opt.param_groups:
            g["lr"], g["weight_decay"] = float(eta[step]), float(lam[step])
        opt.zero_grad(set_to_none=True)
        lossf(model(xtr), ytr).backward()
        opt.step()
    evaluate(T)

    steps = np.array(log["step"])
    t_mem = first_persistent(steps, log["train_acc"])
    t_gen = first_persistent(steps, log["test_acc"])
    summary = {
        "run_id": run_id, "task": task, "cond": cond, "seed": seed, "T": T,
        "t_mem": t_mem, "t_gen": t_gen,
        "B_mem": float(B[t_mem]) if t_mem is not None else None,
        "B_gen": float(B[t_gen]) if t_gen is not None else None,
        "B_total": float(B[-1]),
        "final_test_acc": log["test_acc"][-1], "max_test_acc": max(log["test_acc"]),
        "final_train_acc": log["train_acc"][-1],
        "seconds": round(time.time() - start, 1), "device": dev,
        "setting": {"P": P, "train_frac": TRAIN_FRAC, "split_seed": SPLIT_SEED, "layers": LAYERS},
    }
    np.savez_compressed(out / "curves.npz", **{k: np.array(v) for k, v in log.items()})
    (out / "summary.json").write_text(json.dumps(summary))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
