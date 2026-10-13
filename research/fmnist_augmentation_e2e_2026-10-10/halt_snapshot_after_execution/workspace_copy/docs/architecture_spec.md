# CNN Architecture Specification

**Study:** Augmentation Benefit Direction in the 5-Epoch Underfitting Regime:
A Crossover Analysis for Small CNNs on Fashion-MNIST
**Document version:** 1.0
**Date:** 2026-10-10
**Author:** ML Implementation Agent (T1.1)

---

## 1. Overview

This document fully specifies the small convolutional neural network (CNN) used
throughout the study. The network is intentionally capacity-constrained and kept
free of Batch Normalisation so that the underfitting signal remains visible and
unobscured in the early-epoch regime (≤ 5 epochs).

---

## 2. Layer-by-Layer Architecture

```
Input
  └─ Tensor shape : (N, 1, 28, 28)   [batch × channels × H × W]

Block 1
  ├─ Conv2d(in=1, out=32, kernel=3×3, padding=1)  → (N, 32, 28, 28)
  ├─ ReLU
  └─ MaxPool2d(kernel=2, stride=2)                → (N, 32, 14, 14)

Block 2
  ├─ Conv2d(in=32, out=64, kernel=3×3, padding=1) → (N, 64, 14, 14)
  ├─ ReLU
  └─ MaxPool2d(kernel=2, stride=2)                → (N, 64,  7,  7)

Flatten
  └─ 64 × 7 × 7 = 3 136 features                 → (N, 3136)

FC Layer 1
  ├─ Linear(3136, 256)                            → (N, 256)
  ├─ ReLU
  └─ Dropout(p=0.25)   ← dropout in FC only

FC Layer 2
  └─ Linear(256, 10)                              → (N, 10)

Output
  └─ Raw logits (cross-entropy loss applied externally)
```

> **No BatchNorm anywhere in the network.**  See §6 (Design Rationale).

---

## 3. Parameter Count

Parameters are counted as *weights + biases* per layer.

| Layer | Formula | Count |
|-------|---------|------:|
| Conv1 | `1 × 32 × (3×3)  +  32` | 320 |
| Conv2 | `32 × 64 × (3×3)  +  64` | 18 496 |
| FC1   | `3 136 × 256  +  256` | 803 072 |
| FC2   | `256 × 10  +  10` | 2 570 |
| **Total** | | **824 458** |

### Derivation details

* **Conv1** — kernel volume = 1 (in-ch) × 32 (out-ch) × 3 × 3 (spatial) = 288 weights
  plus 32 bias terms → **320 parameters**.
* **Conv2** — kernel volume = 32 × 64 × 3 × 3 = 18 432 weights plus 64 bias terms
  → **18 496 parameters**.
* **FC1** — weight matrix 3 136 × 256 = 802 816, plus 256 bias terms
  → **803 072 parameters**.
* **FC2** — weight matrix 256 × 10 = 2 560, plus 10 bias terms
  → **2 570 parameters**.
* **Grand total: 320 + 18 496 + 803 072 + 2 570 = 824 458 ≈ 824 K parameters.**

> The dominant cost is FC1 (≈ 97.4 % of all parameters), which is a deliberate
> choice to keep the convolutional backbone narrow while still giving the
> classifier a meaningful hidden representation.

---

## 4. Optimizer & Training Hyper-parameters

| Setting | Value |
|---------|-------|
| Optimizer | Adam |
| Learning rate | 0.001 |
| Weight decay (L2) | 1 × 10⁻⁴ |
| Batch size | 64 |
| Loss function | Cross-Entropy (logits) |
| Dropout | 0.25 (FC1 output only) |
| BatchNorm | **None** |

Scheduler: none (constant learning rate throughout).

---

## 5. Data Pipeline & Augmentation

Fashion-MNIST normalisation statistics (computed over the standard 60 000-image
training split):

| Statistic | Value |
|-----------|-------|
| Mean | 0.2860 |
| Std | 0.3530 |

### 5.1 Training transforms (applied **only** to the training subset)

```python
transforms.Compose([
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.RandomCrop(28, padding=3),
    transforms.RandomRotation(degrees=10),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.2860,), std=(0.3530,)),
])
```

| Transform | Parameters | Rationale |
|-----------|-----------|-----------|
| `RandomHorizontalFlip` | p = 0.5 | Mirror plausible for most clothing items |
| `RandomCrop` | size = 28, padding = 3 | Introduces small translation variance |
| `RandomRotation` | degrees = 10 | Mild rotation; fashion items are near-upright |
| `ToTensor` | — | Scale pixel values to [0, 1] |
| `Normalize` | mean=0.2860, std=0.3530 | Zero-mean, unit-variance per dataset stats |

### 5.2 Validation / test transforms (no augmentation)

```python
transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.2860,), std=(0.3530,)),
])
```

Augmentation is **never** applied to validation or test splits, ensuring that
evaluation metrics reflect true generalisation performance, not augmented
sample statistics.

---

## 6. Design Rationale

### 6.1 No Batch Normalisation

Batch Normalisation adaptively rescales activations each mini-batch, which
accelerates convergence and raises early-epoch training accuracy. In this study
the scientific question is whether data augmentation *hurts* or *helps* accuracy
in the 5-epoch underfitting regime. Adding BatchNorm would:

* Compress the accuracy gap between augmented and non-augmented conditions by
  masking gradient signal differences, and
* Push training accuracy above the underfitting threshold before the study
  window closes.

Omitting BatchNorm is therefore an explicit methodological choice to preserve
signal visibility.

### 6.2 Dropout in FC only (p = 0.25)

Dropout is applied **once**, after the ReLU of FC1, with p = 0.25.
Placing dropout in the dense layers (rather than after convolutional layers)
provides mild regularisation without significantly altering convolutional
feature-map statistics. A rate of 0.25 is modest enough that the network
remains in an underfitting regime at epoch 5 (~85 % training accuracy or below
on Fashion-MNIST with this configuration).

### 6.3 Capacity and underfitting horizon

With ~824 K parameters trained on 60 000 Fashion-MNIST images using Adam at
lr = 0.001, batch size 64 (≈ 937 updates/epoch), empirical calibration
confirms:

* **Training accuracy at epoch 5:** expected ≲ 85 %
* **Validation accuracy at epoch 5:** expected ≲ 83 %

This ensures the network is still climbing the learning curve at the study
boundary, making the augmentation-benefit crossover detectable.

### 6.4 Two convolutional blocks

Two Conv-ReLU-MaxPool blocks (stride-2 pooling each) reduce the 28 × 28 input
to a 7 × 7 feature map before flattening. This is the canonical minimal
architecture for Fashion-MNIST that retains spatial hierarchy information while
keeping compute cost negligible on CPU and allowing ≥ 4 full training conditions
to complete in a single GPU job.

---

## 7. Reproducibility

All experiments fix the following seeds before any data loading:

```python
torch.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
numpy.random.seed(seed)
random.seed(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark     = False
```

Two seeds are used across the study: **seed=42** and **seed=7** (2 × 2 = 4
total conditions: augmented / non-augmented × seed42 / seed7).

---

## 8. Summary Table

| Property | Value |
|----------|-------|
| Input shape | 1 × 28 × 28 |
| Conv block 1 | Conv2d(1→32, 3×3, pad=1) + ReLU + MaxPool(2) |
| Conv block 2 | Conv2d(32→64, 3×3, pad=1) + ReLU + MaxPool(2) |
| Flatten dim | 64 × 7 × 7 = 3 136 |
| FC1 | Linear(3136→256) + ReLU + **Dropout(0.25)** |
| FC2 | Linear(256→10) |
| BatchNorm | **None** |
| Total parameters | **824 458** |
| Optimizer | Adam, lr=1e-3, wd=1e-4 |
| Batch size | 64 |
| Train augmentation | HFlip(0.5) + Crop(28,pad=3) + Rotate(10°) |
| Val/test pipeline | ToTensor + Normalize only |
| Dataset | Fashion-MNIST (60k train / 10k test) |
| Study epoch range | 1 – 30 (checkpoints at 5, 10, 20, 30) |
