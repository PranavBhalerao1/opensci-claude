"""
scripts/crossover_analysis.py
Crossover analysis for the augmentation benefit direction study.

Computes:
  - accuracy_gap = test_acc_aug − test_acc_noaug  for every (seed, epoch)
  - mean_gap across seeds for each epoch
  - First crossover epoch: first epoch where mean_gap > 0 for ≥ 3 consecutive epochs
  - Epoch-5 regime classification:
        underfitting-penalty-confirmed  → mean_gap < 0 at ep5 AND no crossover by ep30
        mixed                           → mean_gap ≈ 0 at ep5 (|gap| < 0.5)
        early-benefit                   → mean_gap > 0 at ep5
  - Train-val divergence at epochs 5 and 30 as supporting evidence
      (using train_loss as training-fit proxy and val_acc as generalisation proxy)

All key numbers are validated against the raw combined_metrics.csv.

Provenance:
  Input  : analysis/combined_metrics.csv  (aggregated from T2.1 GPU runs, 2026-10-10)
  Script : scripts/crossover_analysis.py
  Run    : 2026-10-10
"""

import os, json
import numpy as np
import pandas as pd

# ── 1. Load combined metrics ──────────────────────────────────────────────────
df = pd.read_csv("analysis/combined_metrics.csv")
assert df.shape == (120, 6), f"Unexpected shape: {df.shape}"
assert df.isna().sum().sum() == 0
print(f"Loaded combined_metrics.csv  shape={df.shape}")

# ── 2. Pivot to wide form: one row per (seed, epoch) ─────────────────────────
noaug  = df[df["augmented"] == False].copy()
aug    = df[df["augmented"] == True].copy()
merged = noaug.merge(aug, on=["seed", "epoch"], suffixes=("_noaug", "_aug"))
merged = merged.sort_values(["seed", "epoch"]).reset_index(drop=True)
print(f"Merged (seed × epoch) shape  : {merged.shape}")   # expect 60 rows

# ── 3. Accuracy gap ───────────────────────────────────────────────────────────
merged["accuracy_gap"] = merged["test_acc_aug"] - merged["test_acc_noaug"]

# ── 4. Mean gap across seeds for each epoch ───────────────────────────────────
mean_gap = (
    merged.groupby("epoch")["accuracy_gap"]
    .mean()
    .rename("mean_gap")
    .reset_index()
    .sort_values("epoch")
    .reset_index(drop=True)
)
print("\nFull mean_gap trajectory:")
print(mean_gap.to_string(index=False))

# ── 5. Crossover criterion ────────────────────────────────────────────────────
#  First epoch E such that mean_gap[E], mean_gap[E+1], mean_gap[E+2] are all > 0.
crossover_epoch = None
gaps = mean_gap.set_index("epoch")["mean_gap"]

for ep in range(1, 29):   # need E, E+1, E+2 all within 1–30
    if (
        gaps.get(ep,     -np.inf) > 0 and
        gaps.get(ep + 1, -np.inf) > 0 and
        gaps.get(ep + 2, -np.inf) > 0
    ):
        crossover_epoch = ep
        break

print(f"\nCrossover epoch (first of 3 consecutive mean_gap > 0): "
      f"{crossover_epoch if crossover_epoch else 'NOT FOUND within epochs 1–30'}")

# ── 6. Epoch-5 regime classification ─────────────────────────────────────────
gap_at_5 = float(gaps[5])
print(f"\nmean_gap at epoch 5 = {gap_at_5:.4f} pp")

if crossover_epoch is None and gap_at_5 < 0:
    regime = "underfitting-penalty-confirmed"
elif abs(gap_at_5) < 0.5:
    regime = "mixed"
elif gap_at_5 > 0:
    regime = "early-benefit"
else:
    regime = "underfitting-penalty-confirmed"

print(f"Epoch-5 regime classification : {regime}")

# ── 7. Per-seed gaps at key epochs ───────────────────────────────────────────
print("\nPer-seed accuracy_gap at key epochs:")
key_epochs = [5, 10, 20, 30]
per_seed = merged[merged["epoch"].isin(key_epochs)][
    ["seed", "epoch", "test_acc_noaug", "test_acc_aug", "accuracy_gap"]
].sort_values(["epoch", "seed"])
print(per_seed.to_string(index=False))

# ── 8. Train-val divergence (supporting evidence) ────────────────────────────
print("\n── Train-val divergence supporting evidence ──")
for ep in [5, 30]:
    for seed in [42, 123]:
        row_noaug = df[(df["seed"]==seed)&(df["augmented"]==False)&(df["epoch"]==ep)].iloc[0]
        row_aug   = df[(df["seed"]==seed)&(df["augmented"]==True) &(df["epoch"]==ep)].iloc[0]
        tl_diff = row_aug["train_loss"] - row_noaug["train_loss"]
        va_diff = row_aug["val_acc"]    - row_noaug["val_acc"]
        print(f"  ep={ep:2d} seed={seed}: "
              f"train_loss noaug={row_noaug['train_loss']:.4f}  aug={row_aug['train_loss']:.4f}  "
              f"Δtrain_loss={tl_diff:+.4f}   "
              f"val_acc noaug={row_noaug['val_acc']:.2f}  aug={row_aug['val_acc']:.2f}  "
              f"Δval_acc={va_diff:+.2f}")

# ── 9. Raw-CSV cross-check ────────────────────────────────────────────────────
print("\n── Raw-CSV cross-check against T2.1 reported values ──")
raw_checks = {
    (42,  False,  5): 91.30,  (42,  True,  5): 89.15,
    (123, False,  5): 91.76,  (123, True,  5): 88.51,
    (42,  False, 30): 92.65,  (42,  True, 30): 91.28,
    (123, False, 30): 92.26,  (123, True, 30): 91.00,
}
all_ok = True
for (seed, aug_flag, ep), expected in raw_checks.items():
    rows = df[(df["seed"]==seed)&(df["augmented"]==aug_flag)&(df["epoch"]==ep)]
    assert len(rows) == 1
    actual = float(rows["test_acc"].iloc[0])
    ok = abs(actual - expected) < 0.005
    if not ok:
        all_ok = False
    print(f"  seed={seed} aug={aug_flag} ep={ep:2d}: expected={expected:.2f}  "
          f"actual={actual:.2f}  {'✓' if ok else '✗ MISMATCH'}")
print(f"All raw-CSV checks passed: {all_ok}")

# ── 10. Save outputs ──────────────────────────────────────────────────────────
os.makedirs("analysis", exist_ok=True)

mean_gap.to_csv("analysis/accuracy_gap_trajectory.csv", index=False)

per_seed_all = merged[["seed","epoch","test_acc_noaug","test_acc_aug","accuracy_gap"]].copy()
per_seed_all.to_csv("analysis/per_seed_accuracy_gap.csv", index=False)

def _tv(seed, aug_flag, ep, col):
    return float(df[(df["seed"]==seed)&(df["augmented"]==aug_flag)&(df["epoch"]==ep)][col].iloc[0])

summary = {
    "crossover_epoch": crossover_epoch,
    "epoch5_mean_gap_pp":  round(gap_at_5, 4),
    "epoch5_regime":       regime,
    "gap_seed42_ep5":      round(float(merged[(merged["seed"]==42) &(merged["epoch"]==5) ]["accuracy_gap"].iloc[0]), 4),
    "gap_seed123_ep5":     round(float(merged[(merged["seed"]==123)&(merged["epoch"]==5) ]["accuracy_gap"].iloc[0]), 4),
    "gap_seed42_ep30":     round(float(merged[(merged["seed"]==42) &(merged["epoch"]==30)]["accuracy_gap"].iloc[0]), 4),
    "gap_seed123_ep30":    round(float(merged[(merged["seed"]==123)&(merged["epoch"]==30)]["accuracy_gap"].iloc[0]), 4),
    # Train-val divergence supporting evidence
    "delta_train_loss_ep5_seed42":    round(_tv(42, True,5,"train_loss") - _tv(42, False,5,"train_loss"), 4),
    "delta_train_loss_ep5_seed123":   round(_tv(123,True,5,"train_loss") - _tv(123,False,5,"train_loss"), 4),
    "delta_train_loss_ep30_seed42":   round(_tv(42, True,30,"train_loss")- _tv(42, False,30,"train_loss"),4),
    "delta_train_loss_ep30_seed123":  round(_tv(123,True,30,"train_loss")- _tv(123,False,30,"train_loss"),4),
    "delta_val_acc_ep5_seed42":       round(_tv(42, True,5,"val_acc")   - _tv(42, False,5,"val_acc"),  4),
    "delta_val_acc_ep5_seed123":      round(_tv(123,True,5,"val_acc")   - _tv(123,False,5,"val_acc"),  4),
    "delta_val_acc_ep30_seed42":      round(_tv(42, True,30,"val_acc")  - _tv(42, False,30,"val_acc"), 4),
    "delta_val_acc_ep30_seed123":     round(_tv(123,True,30,"val_acc")  - _tv(123,False,30,"val_acc"), 4),
}

with open("analysis/crossover_summary.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=str)

print("\n── Files written ──")
print("  analysis/combined_metrics.csv")
print("  analysis/accuracy_gap_trajectory.csv")
print("  analysis/per_seed_accuracy_gap.csv")
print("  analysis/crossover_summary.json")
print(f"\n=== FINAL RESULT ===")
print(f"  Crossover epoch : {crossover_epoch if crossover_epoch else 'None (no crossover within 30 epochs)'}")
print(f"  Epoch-5 mean_gap: {gap_at_5:.2f} pp")
print(f"  Epoch-5 regime  : {regime}")
