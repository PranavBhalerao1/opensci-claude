
import pandas as pd
import numpy as np
import os

df = pd.read_csv("analysis/test_acc_summary.csv")

# Convert fractions → percentage points
df["acc_noaug_pp"] = df["acc_noaug"] * 100.0
df["acc_aug_pp"]   = df["acc_aug"]   * 100.0
df["delta"]        = df["acc_aug_pp"] - df["acc_noaug_pp"]

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

    rows.append({
        "size"          : int(sz),
        "delta_seed42"  : round(d42,    4),
        "delta_seed123" : round(d123,   4),
        "delta_mean"    : round((d42 + d123) / 2.0,    4),
        "delta_range"   : round(abs(d42 - d123),       4),
        "acc_noaug_mean": round((n42 + n123) / 2.0,    4),
        "acc_aug_mean"  : round((a42 + a123) / 2.0,    4),
    })

result = pd.DataFrame(rows)

# Verify
assert len(result) == 7
required_cols = ["size","delta_seed42","delta_seed123","delta_mean",
                 "delta_range","acc_noaug_mean","acc_aug_mean"]
for c in required_cols:
    assert c in result.columns
    assert result[c].notna().all()
    assert np.isfinite(result[c]).all()

os.makedirs("analysis", exist_ok=True)
result.to_csv("analysis/delta_by_size.csv", index=False)
print("Saved → analysis/delta_by_size.csv")
print("\nFull table:")
print(result.to_string(index=False))
