
import os, json
import numpy as np
import pandas as pd

# ── Re-run the full analysis with the bug-fix ──────────────────────────────────

df = pd.read_csv("analysis/combined_metrics.csv")

noaug = df[df["augmented"] == False].copy()
aug   = df[df["augmented"] == True].copy()

merged = noaug.merge(aug, on=["seed", "epoch"], suffixes=("_noaug", "_aug"))
merged = merged.sort_values(["seed", "epoch"]).reset_index(drop=True)

merged["accuracy_gap"] = merged["test_acc_aug"] - merged["test_acc_noaug"]

mean_gap = (
    merged.groupby("epoch")["accuracy_gap"]
    .mean()
    .rename("mean_gap")
    .reset_index()
    .sort_values("epoch")
    .reset_index(drop=True)
)

gaps = mean_gap.set_index("epoch")["mean_gap"]

# Crossover criterion
crossover_epoch = None
for ep in range(1, 29):
    if (
        gaps.get(ep,     -np.inf) > 0 and
        gaps.get(ep + 1, -np.inf) > 0 and
        gaps.get(ep + 2, -np.inf) > 0
    ):
        crossover_epoch = ep
        break

gap_at_5 = float(gaps[5])

if crossover_epoch is None and gap_at_5 < 0:
    regime = "underfitting-penalty-confirmed"
elif abs(gap_at_5) < 0.5:
    regime = "mixed"
elif gap_at_5 > 0:
    regime = "early-benefit"
else:
    regime = "underfitting-penalty-confirmed"

# ── Raw-CSV cross-check (fixed indexing) ──────────────────────────────────────
raw_checks = {
    (42,  False, 5):  91.30,
    (42,  True,  5):  89.15,
    (123, False, 5):  91.76,
    (123, True,  5):  88.51,
    (42,  False, 30): 92.65,
    (42,  True,  30): 91.28,
    (123, False, 30): 92.26,
    (123, True,  30): 91.00,
}

print("── Raw-CSV cross-check ──")
all_ok = True
for (seed, aug_flag, ep), expected in raw_checks.items():
    rows = df[(df["seed"] == seed) & (df["augmented"] == aug_flag) & (df["epoch"] == ep)]
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)} for seed={seed} aug={aug_flag} ep={ep}"
    actual = float(rows["test_acc"].iloc[0])
    ok = abs(actual - expected) < 0.005
    if not ok:
        all_ok = False
    print(f"  seed={seed} aug={aug_flag} ep={ep:2d}: expected={expected:.2f}  actual={actual:.2f}  {'✓' if ok else '✗ MISMATCH'}")

print(f"\nAll raw-CSV checks passed: {all_ok}")

# ── Save outputs ───────────────────────────────────────────────────────────────
os.makedirs("analysis", exist_ok=True)

mean_gap.to_csv("analysis/accuracy_gap_trajectory.csv", index=False)

per_seed_all = merged[["seed", "epoch", "test_acc_noaug", "test_acc_aug", "accuracy_gap"]].copy()
per_seed_all.to_csv("analysis/per_seed_accuracy_gap.csv", index=False)

summary = {
    "crossover_epoch": crossover_epoch,        # None → no crossover within 30 epochs
    "epoch5_mean_gap_pp":  round(gap_at_5, 4),
    "epoch5_regime":       regime,
    "gap_seed42_ep5":   round(float(merged[(merged["seed"]==42)  & (merged["epoch"]==5) ]["accuracy_gap"].iloc[0]), 4),
    "gap_seed123_ep5":  round(float(merged[(merged["seed"]==123) & (merged["epoch"]==5) ]["accuracy_gap"].iloc[0]), 4),
    "gap_seed42_ep30":  round(float(merged[(merged["seed"]==42)  & (merged["epoch"]==30)]["accuracy_gap"].iloc[0]), 4),
    "gap_seed123_ep30": round(float(merged[(merged["seed"]==123) & (merged["epoch"]==30)]["accuracy_gap"].iloc[0]), 4),
    # Train-val divergence support
    "delta_train_loss_ep5_seed42":   round(
        float(df[(df["seed"]==42) &(df["augmented"]==True) &(df["epoch"]==5)]["train_loss"].iloc[0]) -
        float(df[(df["seed"]==42) &(df["augmented"]==False)&(df["epoch"]==5)]["train_loss"].iloc[0]), 4),
    "delta_train_loss_ep5_seed123":  round(
        float(df[(df["seed"]==123)&(df["augmented"]==True) &(df["epoch"]==5)]["train_loss"].iloc[0]) -
        float(df[(df["seed"]==123)&(df["augmented"]==False)&(df["epoch"]==5)]["train_loss"].iloc[0]), 4),
    "delta_train_loss_ep30_seed42":  round(
        float(df[(df["seed"]==42) &(df["augmented"]==True) &(df["epoch"]==30)]["train_loss"].iloc[0]) -
        float(df[(df["seed"]==42) &(df["augmented"]==False)&(df["epoch"]==30)]["train_loss"].iloc[0]), 4),
    "delta_train_loss_ep30_seed123": round(
        float(df[(df["seed"]==123)&(df["augmented"]==True) &(df["epoch"]==30)]["train_loss"].iloc[0]) -
        float(df[(df["seed"]==123)&(df["augmented"]==False)&(df["epoch"]==30)]["train_loss"].iloc[0]), 4),
    "delta_val_acc_ep5_seed42":   round(
        float(df[(df["seed"]==42) &(df["augmented"]==True) &(df["epoch"]==5)]["val_acc"].iloc[0]) -
        float(df[(df["seed"]==42) &(df["augmented"]==False)&(df["epoch"]==5)]["val_acc"].iloc[0]), 4),
    "delta_val_acc_ep5_seed123":  round(
        float(df[(df["seed"]==123)&(df["augmented"]==True) &(df["epoch"]==5)]["val_acc"].iloc[0]) -
        float(df[(df["seed"]==123)&(df["augmented"]==False)&(df["epoch"]==5)]["val_acc"].iloc[0]), 4),
    "delta_val_acc_ep30_seed42":  round(
        float(df[(df["seed"]==42) &(df["augmented"]==True) &(df["epoch"]==30)]["val_acc"].iloc[0]) -
        float(df[(df["seed"]==42) &(df["augmented"]==False)&(df["epoch"]==30)]["val_acc"].iloc[0]), 4),
    "delta_val_acc_ep30_seed123": round(
        float(df[(df["seed"]==123)&(df["augmented"]==True) &(df["epoch"]==30)]["val_acc"].iloc[0]) -
        float(df[(df["seed"]==123)&(df["augmented"]==False)&(df["epoch"]==30)]["val_acc"].iloc[0]), 4),
}

with open("analysis/crossover_summary.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=str)

print("\nFiles written:")
print("  analysis/accuracy_gap_trajectory.csv")
print("  analysis/per_seed_accuracy_gap.csv")
print("  analysis/crossover_summary.json")
