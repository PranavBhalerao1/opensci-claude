
import pandas as pd
import numpy as np

print("=" * 65)
print("STEP 3: Full accuracy trajectory summary (all four runs)")
print("=" * 65)

csv_files = {
    "seed42_noaug":  "data/metrics_seed42_noaug.csv",
    "seed42_aug":    "data/metrics_seed42_aug.csv",
    "seed123_noaug": "data/metrics_seed123_noaug.csv",
    "seed123_aug":   "data/metrics_seed123_aug.csv",
}

print(f"\n{'Condition':<18} {'Ep':>3} {'train_loss':>10} {'train_acc':>10} "
      f"{'val_acc':>9} {'test_acc':>10}")
print("-" * 65)

for label, path in csv_files.items():
    df = pd.read_csv(path, comment="#")
    for ep in [1, 5, 10, 15, 20, 25, 30]:
        row = df[df["epoch"] == ep].iloc[0]
        marker = " ◄" if ep in [5, 30] else ""
        print(f"  {label:<16} {ep:3d}  "
              f"{row['train_loss']:10.4f} {row['train_acc']:10.4f} "
              f"{row['val_acc']:9.4f} {row['test_acc']:10.4f}{marker}")
    print()
    
print("=" * 65)
print("STEP 4: Epoch-5 vs Epoch-30 test_acc gap (noaug − aug)")
print("=" * 65)

for seed in [42, 123]:
    df_noaug = pd.read_csv(f"data/metrics_seed{seed}_noaug.csv", comment="#")
    df_aug   = pd.read_csv(f"data/metrics_seed{seed}_aug.csv",   comment="#")
    
    for ep in [5, 10, 20, 30]:
        noaug_acc = df_noaug[df_noaug["epoch"]==ep]["test_acc"].values[0]
        aug_acc   = df_aug  [df_aug  ["epoch"]==ep]["test_acc"].values[0]
        gap       = (noaug_acc - aug_acc) * 100
        direction = "noaug>aug" if gap > 0 else "aug>noaug"
        print(f"  seed={seed} ep={ep:2d}:  noaug={noaug_acc*100:.2f}%  "
              f"aug={aug_acc*100:.2f}%  gap={gap:+.2f}pp  [{direction}]")
    print()
