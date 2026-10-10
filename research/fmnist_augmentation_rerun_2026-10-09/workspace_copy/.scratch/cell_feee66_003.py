
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

os.makedirs("figures", exist_ok=True)
os.makedirs("paper",   exist_ok=True)
os.makedirs("results", exist_ok=True)

# ── load data ────────────────────────────────────────────────────────────────
acc  = pd.read_csv("analysis/test_acc_summary.csv")
delt = pd.read_csv("analysis/delta_by_size.csv")
with open("analysis/regression_results.json") as f:
    reg = json.load(f)

gpu_txt  = open("analysis/gpu_device_info.txt").read()
diag_txt = open("analysis/trend_diagnostics.txt").read()

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE: figures/fig_test_acc_bars.png
# ═══════════════════════════════════════════════════════════════════════════
sizes   = sorted(acc["size"].unique())
n_sizes = len(sizes)
x       = np.arange(n_sizes)
bar_w   = 0.36
gap     = 0.04

noaug_mean = [acc[acc["size"]==s]["acc_noaug"].mean()*100 for s in sizes]
aug_mean   = [acc[acc["size"]==s]["acc_aug"].mean()*100   for s in sizes]
noaug_s42  = [acc[(acc["size"]==s)&(acc["seed"]==42)]["acc_noaug"].values[0]*100  for s in sizes]
noaug_s123 = [acc[(acc["size"]==s)&(acc["seed"]==123)]["acc_noaug"].values[0]*100 for s in sizes]
aug_s42    = [acc[(acc["size"]==s)&(acc["seed"]==42)]["acc_aug"].values[0]*100    for s in sizes]
aug_s123   = [acc[(acc["size"]==s)&(acc["seed"]==123)]["acc_aug"].values[0]*100   for s in sizes]

C_NOAUG = "#3A7DC9"
C_AUG   = "#E8820C"
DOT_KW  = dict(zorder=5, clip_on=False)

fig, ax = plt.subplots(figsize=(10, 5.5))

ax.bar(x - (bar_w/2 + gap/2), noaug_mean, bar_w,
       color=C_NOAUG, alpha=0.82, label="No Augmentation",
       edgecolor="white", linewidth=0.6)
ax.bar(x + (bar_w/2 + gap/2), aug_mean,   bar_w,
       color=C_AUG,   alpha=0.82, label="With Augmentation",
       edgecolor="white", linewidth=0.6)

jitter = 0.07
ax.scatter(x - (bar_w/2 + gap/2) - jitter, noaug_s42,  marker='o', s=38,
           color="white", edgecolors=C_NOAUG, linewidths=1.4, **DOT_KW)
ax.scatter(x - (bar_w/2 + gap/2) + jitter, noaug_s123, marker='s', s=38,
           color="white", edgecolors=C_NOAUG, linewidths=1.4, **DOT_KW)
ax.scatter(x + (bar_w/2 + gap/2) - jitter, aug_s42,    marker='o', s=38,
           color="white", edgecolors=C_AUG,   linewidths=1.4, **DOT_KW)
ax.scatter(x + (bar_w/2 + gap/2) + jitter, aug_s123,   marker='s', s=38,
           color="white", edgecolors=C_AUG,   linewidths=1.4, **DOT_KW)

ax.set_xticks(x)
ax.set_xticklabels([f"{s:,}" for s in sizes], fontsize=10)
ax.set_xlabel("Training Set Size  N", fontsize=12, labelpad=6)
ax.set_ylabel("Test Accuracy  (%)", fontsize=12, labelpad=6)
ax.set_title("Final Test Accuracy by Training Size and Augmentation Condition\n"
             "(Fashion-MNIST · 5-epoch CNN · mean of 2 seeds)", fontsize=12, pad=10)
ax.set_ylim(58, 97)
ax.yaxis.set_major_locator(mticker.MultipleLocator(5))
ax.yaxis.set_minor_locator(mticker.MultipleLocator(1))
ax.grid(axis="y", which="major", linestyle="--", linewidth=0.6, alpha=0.55)
ax.grid(axis="y", which="minor", linestyle=":",  linewidth=0.3, alpha=0.35)
ax.set_axisbelow(True)
ax.spines[["top","right"]].set_visible(False)

# Δ annotation above each pair
for i, (nm, am, row) in enumerate(zip(noaug_mean, aug_mean,
                                       delt.sort_values("size").itertuples())):
    top = max(nm, am)
    ax.text(x[i], top + 0.7, f"Δ={row.delta_mean:+.1f}pp",
            ha="center", va="bottom", fontsize=7.5, color="#555555", style="italic")

legend_handles = [
    plt.Rectangle((0,0),1,1, color=C_NOAUG, alpha=0.82, label="No Augmentation"),
    plt.Rectangle((0,0),1,1, color=C_AUG,   alpha=0.82, label="With Augmentation"),
    Line2D([0],[0], marker='o', color='w', markeredgecolor='#666', markerfacecolor='w',
           markersize=7, linewidth=0, label="Seed 42"),
    Line2D([0],[0], marker='s', color='w', markeredgecolor='#666', markerfacecolor='w',
           markersize=7, linewidth=0, label="Seed 123"),
]
ax.legend(handles=legend_handles, loc="lower right", fontsize=9,
          framealpha=0.92, edgecolor="#cccccc")

plt.tight_layout()
fig.savefig("figures/fig_test_acc_bars.png", dpi=150, bbox_inches="tight")
plt.close()
fsize = os.path.getsize("figures/fig_test_acc_bars.png")
print(f"✓ figures/fig_test_acc_bars.png  ({fsize/1024:.1f} KB)")
assert fsize > 10_000
