
import pandas as pd
import numpy as np

# ── 1. Load ───────────────────────────────────────────────────────────────────
df = pd.read_csv("analysis/test_acc_summary.csv")

# ── 2. Convert fractions → percentage points ──────────────────────────────────
# Values are in [0,1], so multiply by 100
df["acc_noaug_pp"] = df["acc_noaug"] * 100.0
df["acc_aug_pp"]   = df["acc_aug"]   * 100.0
df["delta"]        = df["acc_aug_pp"] - df["acc_noaug_pp"]   # Δ = aug − noaug

print("Per-(size, seed) delta [pp]:")
print(df[["size","seed","acc_noaug_pp","acc_aug_pp","delta"]].to_string(index=False))

# ── 3. Pivot to wide format, one row per size ─────────────────────────────────
seed42  = df[df["seed"]==42 ].set_index("size")
seed123 = df[df["seed"]==123].set_index("size")

sizes = sorted(df["size"].unique())

rows = []
for sz in sizes:
    d42   = seed42.loc[sz,  "delta"]
    d123  = seed123.loc[sz, "delta"]
    n42   = seed42.loc[sz,  "acc_noaug_pp"]
    n123  = seed123.loc[sz, "acc_noaug_pp"]
    a42   = seed42.loc[sz,  "acc_aug_pp"]
    a123  = seed123.loc[sz, "acc_aug_pp"]

    d_mean  = (d42 + d123) / 2.0
    d_range = abs(d42 - d123)
    n_mean  = (n42 + n123) / 2.0
    a_mean  = (a42 + a123) / 2.0

    rows.append({
        "size"         : int(sz),
        "delta_seed42" : round(d42,   4),
        "delta_seed123": round(d123,  4),
        "delta_mean"   : round(d_mean, 4),
        "delta_range"  : round(d_range,4),
        "acc_noaug_mean": round(n_mean, 4),
        "acc_aug_mean"  : round(a_mean, 4),
    })

result = pd.DataFrame(rows)

# ── 4. Flag negative deltas ───────────────────────────────────────────────────
print("\n── Δ by training size (percentage points) ──")
print(f"{'size':>7}  {'Δ_42':>8}  {'Δ_123':>8}  {'Δ_mean':>8}  {'Δ_range':>8}  {'noaug_mean':>11}  {'aug_mean':>9}  FLAG")
print("-"*90)

for _, row in result.iterrows():
    flag = "*** NEGATIVE DELTA ***" if row["delta_mean"] < 0 else ""
    print(f"{int(row['size']):>7}  {row['delta_seed42']:>8.4f}  "
          f"{row['delta_seed123']:>8.4f}  {row['delta_mean']:>8.4f}  "
          f"{row['delta_range']:>8.4f}  {row['acc_noaug_mean']:>11.4f}  "
          f"{row['acc_aug_mean']:>9.4f}  {flag}")

# ── 5. Sanity checks ──────────────────────────────────────────────────────────
assert len(result) == 7, f"Expected 7 rows, got {len(result)}"
required_cols = ["size","delta_seed42","delta_seed123","delta_mean","delta_range","acc_noaug_mean","acc_aug_mean"]
for c in required_cols:
    assert c in result.columns, f"Missing column: {c}"
    assert result[c].notna().all(), f"NaN found in column: {c}"
    assert np.isfinite(result[c]).all(), f"Inf found in column: {c}"

print("\n✓ All sanity checks passed (7 rows, all required cols, no NaN/Inf)")

# ── 6. Save ───────────────────────────────────────────────────────────────────
os.makedirs("analysis", exist_ok=True)
result.to_csv("analysis/delta_by_size.csv", index=False)
print("\nSaved → analysis/delta_by_size.csv")
