# Study Results Summary

**Title:** Augmentation Benefit Direction in the 5-Epoch Underfitting Regime:  
A Crossover Analysis for Small CNNs on Fashion-MNIST

**Generated:** 2026-10-10  
**Agent:** T4.4 — Visualization and Results Engineer

---

## 1. Study Metadata

| Property | Value |
|----------|-------|
| Title | Augmentation Benefit Direction in the 5-Epoch Underfitting Regime |
| Dataset | Fashion-MNIST (60,000 train / 10,000 test) |
| Architecture | Small CNN — 2 conv blocks (32→64 ch), FC(3136→256→10), Dropout(0.25), **no BatchNorm** |
| Total parameters | 824,458 |
| Seeds | 42, 123 |
| Total epochs | 30 |
| Checkpoint epochs | 5, 10, 20, 30 |
| Conditions | No-augmentation vs. Augmentation (HFlip + RandomCrop + Rotate±10°) |
| Optimizer | Adam, lr=1e-3, wd=1e-4, batch=64 |
| Training device | NVIDIA L4 (CUDA 13.0, PyTorch 2.11.0+cu130) |

---

## 2. Key Result: Epoch-5 Accuracy Gap

> **Epoch-5 gap** = test_acc(aug) − test_acc(no-aug), in percentage points (pp).

| Seed | No-aug test acc (%) | Aug test acc (%) | epoch-5 gap (pp) |
|------|--------------------|-----------------:|------------------:|
| Seed 42 | 91.30 | 89.15 | **−2.15** |
| Seed 123 | 91.76 | 88.51 | **−3.25** |
| **Mean** | 91.53 | 88.83 | **−2.70** |

- epoch-5 gap, seed 42 : **−2.15 pp**
- epoch-5 gap, seed 123 : **−3.25 pp**
- epoch-5 gap, mean : **−2.70 pp**

**Regime classification: `underfitting-penalty-confirmed`**  
Both seeds show a strictly negative gap at epoch 5. Data augmentation *hurts* test accuracy
in the 5-epoch underfitting regime for this small CNN. The model has not yet converged;
augmentation roughly doubles training loss (noaug ≈ 0.188 vs. aug ≈ 0.375) at epoch 5,
confirming the model is still underfitting and augmentation acts as an additional
optimization penalty rather than a regularizer.

---

## 3. Crossover Analysis

**Crossover criterion:** First epoch e* such that `mean_gap > 0` for 3 consecutive epochs  
(epochs e*, e*+1, e*+2).

**Result: No crossover within 30 epochs**

All 30 mean_gap values are negative (range: −5.145 pp at epoch 1 to −0.355 pp at epoch 29).
The penalty *narrows* over training but never reverses sign within the 30-epoch run.

### mean_gap at key epochs

| Epoch | mean_gap (pp) |
|-------|--------------|
| 5 | −2.70 |
| 10 | −1.93 |
| 20 | −1.58 |
| 30 | −1.31 |

Closest approach: epoch 29, mean_gap = −0.355 pp (seed 42: −0.80 pp; seed 123: +0.09 pp — 
only a single epoch with positive seed-level gap, not sustained).

---

## 4. Checkpoint Table

Full checkpoint accuracy summary (test accuracy %) at epochs 5, 10, 20, 30.  
Gap = aug − no-aug in percentage points.

| Epoch | No-aug S42 (%) | Aug S42 (%) | Gap S42 (pp) | No-aug S123 (%) | Aug S123 (%) | Gap S123 (pp) | Mean gap (pp) |
|------:|---------------:|------------:|-------------:|----------------:|-------------:|--------------:|--------------:|
| 5 | 91.30 | 89.15 | −2.15 | 91.76 | 88.51 | −3.25 | −2.70 |
| 10 | 92.18 | 90.27 | −1.91 | 92.04 | 90.10 | −1.94 | −1.93 |
| 20 | 92.35 | 90.13 | −2.22 | 92.05 | 91.12 | −0.93 | −1.58 |
| 30 | 92.65 | 91.28 | −1.37 | 92.26 | 91.00 | −1.26 | −1.31 |

**All gap values are negative**: augmentation never achieves parity with no-augmentation
at any of the four checkpoint epochs.

---

## 5. Training Dynamics Summary

### Epoch 5 (underfitting regime confirmed)

| Condition | Seed | train_loss | val_acc (%) | test_acc (%) |
|-----------|------|------------|-------------|--------------|
| No-aug | 42 | 0.1879 | 91.12 | 91.30 |
| Aug | 42 | 0.3761 | 89.26 | 89.15 |
| No-aug | 123 | 0.1880 | 91.72 | 91.76 |
| Aug | 123 | 0.3738 | 88.72 | 88.51 |

Mean Δtrain_loss (aug − no-aug) at epoch 5: **+0.187 pp** — augmentation roughly doubles
training loss, confirming both conditions are in the underfitting regime.

### Epoch 30 (late-training / overfitting-emergence)

| Condition | Seed | train_loss | val_acc (%) | test_acc (%) |
|-----------|------|------------|-------------|--------------|
| No-aug | 42 | 0.0510 | 92.78 | 92.65 |
| Aug | 42 | 0.2774 | 90.82 | 91.28 |
| No-aug | 123 | 0.0474 | 92.40 | 92.26 |
| Aug | 123 | 0.2807 | 91.18 | 91.00 |

Mean Δtrain_loss at epoch 30: **+0.230 pp** (widened from +0.187 at epoch 5).  
val_acc gap narrowed from 2.43 pp → 1.59 pp (epoch 5 → 30) but never reversed.  
No-aug train_loss fell from 0.188 → 0.049 (indicative of overfitting emergence);
aug train_loss remains high (0.375 → 0.279), acting as implicit regularization
but insufficient to overcome no-aug's head start within 30 epochs.

---

## 6. Figure Inventory

| Figure | Description | PNG | PDF |
|--------|-------------|-----|-----|
| fig1 | Test accuracy curves for all 4 conditions (2 seeds × 2 aug settings) over 30 epochs, with epoch-5 marker | `figures/fig1_test_accuracy_curves.png` | `figures/fig1_test_accuracy_curves.pdf` |
| fig2 | Accuracy gap trajectory (aug − no-aug) per seed and mean, with epoch-5 marker and zero-crossover reference | `figures/fig2_accuracy_gap.png` | `figures/fig2_accuracy_gap.pdf` |
| fig3 | Training loss and validation accuracy dual-axis curves (2×2 grid: seed × condition) | `figures/fig3_loss_curves.png` | `figures/fig3_loss_curves.pdf` |

Color conventions: blue (#2166AC) = no-aug / seed 42; orange (#D6604D) = aug / seed 123;
solid = seed 42; dashed = seed 123. All figures saved at 300 dpi.

---

## 7. Data Provenance

| Item | Detail |
|------|--------|
| Dataset | Fashion-MNIST — standard torchvision download (60k train / 10k test) |
| GPU device | **NVIDIA L4** (source: `data/gpu_and_data_validation.txt`, accessed 2026-10-10) |
| CUDA version | 13.0 (torch 2.11.0+cu130, torchvision 0.26.0+cu130) |
| Forward pass | PASS — output (64, 10), 824,458 trainable parameters verified |
| Per-epoch CSVs | `data/metrics_seed42_noaug.csv`, `data/metrics_seed42_aug.csv`, `data/metrics_seed123_noaug.csv`, `data/metrics_seed123_aug.csv` |
| Aggregated metrics | `analysis/combined_metrics.csv` (120 rows = 4 conditions × 30 epochs) |
| Gap trajectory | `analysis/gap_trajectory.csv` (30 rows) — T3.2 output |
| Checkpoint stats | `analysis/checkpoint_stats.csv` (4 rows: epochs 5/10/20/30) — T3.2 output |
| Crossover report | `analysis/crossover_report.txt` — T3.3 output |
| All 120 per-epoch cells and 8 checkpoint cells validated exact-match against raw CSVs. |

---

## 8. Analysis Artifacts

| File | Description |
|------|-------------|
| `analysis/table1_checkpoint_summary.csv` | Checkpoint table (4 rows × 8 cols), formatted to 2 d.p. |
| `analysis/table1_checkpoint_summary.tex` | LaTeX tabular with booktabs rules for Table 1 |
| `analysis/gap_trajectory.csv` | Full 30-epoch gap trajectory (per-seed + mean) |
| `analysis/checkpoint_stats.csv` | Checkpoint statistics with train losses |
| `analysis/crossover_report.txt` | Full crossover analysis narrative |
| `analysis/crossover_summary.json` | Machine-readable crossover summary |

---

*End of SUMMARY.md — T4.4 complete.*
