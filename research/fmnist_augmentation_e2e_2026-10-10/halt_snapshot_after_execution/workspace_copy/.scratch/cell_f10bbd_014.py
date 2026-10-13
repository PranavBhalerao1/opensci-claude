
# Print summary of epoch-5 and epoch-30 test accuracies for post_note
import pandas as pd

data = {}
for cond, path in [
    ("seed42_noaug",  "data/metrics_seed42_noaug.csv"),
    ("seed42_aug",    "data/metrics_seed42_aug.csv"),
    ("seed123_noaug", "data/metrics_seed123_noaug.csv"),
    ("seed123_aug",   "data/metrics_seed123_aug.csv"),
]:
    df = pd.read_csv(path, comment="#")
    ep5  = df[df["epoch"]==5].iloc[0]
    ep30 = df[df["epoch"]==30].iloc[0]
    data[cond] = {
        "ep5_test":  round(ep5["test_acc"]*100, 2),
        "ep30_test": round(ep30["test_acc"]*100, 2),
        "ep5_val":   round(ep5["val_acc"]*100, 2),
        "ep30_val":  round(ep30["val_acc"]*100, 2),
    }
    print(f"{cond}: ep5_test={data[cond]['ep5_test']}%  ep30_test={data[cond]['ep30_test']}%")
