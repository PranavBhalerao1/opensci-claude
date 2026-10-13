"""
scripts/aggregate_metrics.py
Aggregates per-epoch metric CSVs from all four training runs into a single
combined_metrics.csv for downstream crossover analysis.

Provenance:
  Source files : data/metrics_seed{42,123}_{aug,noaug}.csv
  Produced by  : T2.1 GPU training job on NVIDIA L4 (2026-10-10)
  Script run   : 2026-10-10
"""

import os
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Load raw CSVs
# ---------------------------------------------------------------------------
# Each CSV was written with the provenance metadata embedded as the first
# column name (e.g. "# seed=42 augment=False device=cuda start=...").
# pd.read_csv() returns exactly 30 data rows per file; the first column
# contains integer epoch numbers.

CONFIGS = [
    ("data/metrics_seed42_noaug.csv",  42,  False),
    ("data/metrics_seed42_aug.csv",    42,  True),
    ("data/metrics_seed123_noaug.csv", 123, False),
    ("data/metrics_seed123_aug.csv",   123, True),
]

frames = []
for path, seed, aug in CONFIGS:
    df = pd.read_csv(path)
    # The first column (epoch numbers) has a metadata-embedded name — rename it
    df = df.rename(columns={df.columns[0]: "epoch"})
    # Attach identifiers
    df.insert(0, "seed", seed)
    df.insert(1, "augmented", aug)
    frames.append(df)
    print(f"  Loaded {path}: {len(df)} rows, epoch range [{df['epoch'].min()}–{df['epoch'].max()}]")

# ---------------------------------------------------------------------------
# 2. Concatenate & select required columns
# ---------------------------------------------------------------------------
combined = pd.concat(frames, ignore_index=True)

# Keep only the six required columns (drop train_acc)
required_cols = ["seed", "augmented", "epoch", "train_loss", "val_acc", "test_acc"]
combined = combined[required_cols]

print(f"\nCombined shape : {combined.shape}")
print(f"Columns        : {combined.columns.tolist()}")

# ---------------------------------------------------------------------------
# 3. Validate
# ---------------------------------------------------------------------------
assert combined.shape[0] == 120, f"Expected 120 rows, got {combined.shape[0]}"

nan_count = combined.isna().sum().sum()
assert nan_count == 0, f"Found {nan_count} NaN values"

acc_min = combined["test_acc"].min()
acc_max = combined["test_acc"].max()
assert 50 <= acc_min and acc_max <= 99, (
    f"test_acc out of [50, 99]: min={acc_min}, max={acc_max}"
)

# Verify 4 unique (seed, augmented) combos each with 30 rows
groups = combined.groupby(["seed", "augmented"]).size()
assert (groups == 30).all(), f"Not all groups have 30 rows:\n{groups}"
assert len(groups) == 4, f"Expected 4 groups, got {len(groups)}"

for (seed, aug), grp in combined.groupby(["seed", "augmented"]):
    epochs = sorted(grp["epoch"].tolist())
    assert epochs == list(range(1, 31)), (
        f"Epoch sequence wrong for seed={seed} aug={aug}: {epochs[:5]}..."
    )

print("\nValidation: ALL CHECKS PASSED")
print(f"  NaN values     : {nan_count}")
print(f"  test_acc range : [{acc_min:.2f}, {acc_max:.2f}]")
print(f"  Groups (seed, augmented) with 30 rows each:\n{groups.to_string()}")

# ---------------------------------------------------------------------------
# 4. Write output
# ---------------------------------------------------------------------------
os.makedirs("analysis", exist_ok=True)
out_path = "analysis/combined_metrics.csv"
combined.to_csv(out_path, index=False)
print(f"\nWritten : {out_path}")

# ---------------------------------------------------------------------------
# 5. Quick sanity — pivot at epochs {5, 10, 20, 30}
# ---------------------------------------------------------------------------
subset = combined[combined["epoch"].isin([5, 10, 20, 30])]
pivot = subset.pivot_table(
    values="test_acc",
    index=["seed", "augmented"],
    columns="epoch",
    aggfunc="mean",
)
print("\nPivot table — mean test_acc by (seed, augmented) at epochs {5, 10, 20, 30}:")
print(pivot.to_string())
