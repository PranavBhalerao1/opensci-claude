
# Also update the scripts/ file to match the final version
script_final = r'''#!/usr/bin/env python3
"""
fig3_loss_curves.py
===================
Produce fig3_loss_curves.png and fig3_loss_curves.pdf:
  2×2 subplot grid (rows=seeds [42, 123], columns=conditions [no-aug, aug])
  with train_loss on left blue y-axis and val_acc on right orange y-axis,
  epoch-5 vertical dashed marker, and epoch-5 value annotations.

Provenance:
  Input : analysis/combined_metrics.csv   (T3.1 output, accessed 2026-10-10)
           analysis/crossover_summary.json (T3.1 output, accessed 2026-10-10)
  Output: figures/fig3_loss_curves.{png,pdf}
  Date  : 2026-10-10
"""
import json, pathlib
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

ROOT    = pathlib.Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

df = pd.read_csv(ROOT / "analysis" / "combined_metrics.csv")
with open(ROOT / "analysis" / "crossover_summary.json") as fh:
    crossover = json.load(fh)

crossover_epoch = crossover["crossover_epoch"]    # None = never crossed over
epoch5_mean_gap = crossover["epoch5_mean_gap_pp"] # -2.70

BLUE_LOSS  = "#2166AC"
ORANGE_ACC = "#D6604D"
GREY_VLINE = "#606060"

plt.rcParams.update({
    "font.family"       : "DejaVu Sans",
    "font.size"         : 10,
    "axes.titlesize"    : 10.5,
    "axes.labelsize"    : 9.5,
    "xtick.labelsize"   : 8.5,
    "ytick.labelsize"   : 8.5,
    "axes.spines.top"   : False,
    "figure.facecolor"  : "white",
    "axes.facecolor"    : "#F9F9F9",
})

SEEDS      = [(42, "Seed 42"), (123, "Seed 123")]
CONDITIONS = [(False, "No Augmentation"), (True, "Augmentation")]

fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)

for ri, (seed, seed_label) in enumerate(SEEDS):
    for ci, (aug_flag, aug_label) in enumerate(CONDITIONS):
        ax_l = axes[ri, ci]
        ax_r = ax_l.twinx()

        sub = df[(df["seed"] == seed) & (df["augmented"] == aug_flag)].sort_values("epoch")
        ep  = sub["epoch"].values
        tl  = sub["train_loss"].values
        va  = sub["val_acc"].values

        ax_l.plot(ep, tl, color=BLUE_LOSS,  lw=2.0, zorder=3)
        ax_r.plot(ep, va, color=ORANGE_ACC, lw=2.0, zorder=3)

        ep5 = sub[sub["epoch"] == 5].iloc[0]
        ax_l.scatter([5], [ep5.train_loss], color=BLUE_LOSS,  s=35, zorder=5)
        ax_r.scatter([5], [ep5.val_acc],    color=ORANGE_ACC, s=35, zorder=5)

        ax_l.axvline(5, color=GREY_VLINE, ls="--", lw=1.4, alpha=0.8, zorder=2)

        ax_l.set_xlim(1, 30)
        ax_l.xaxis.set_major_locator(ticker.MultipleLocator(5))
        ax_l.xaxis.set_minor_locator(ticker.MultipleLocator(1))
        ax_l.tick_params(axis="x", which="both", direction="in")
        ax_l.tick_params(axis="y", colors=BLUE_LOSS)
        ax_r.tick_params(axis="y", colors=ORANGE_ACC)
        ax_r.spines["right"].set_edgecolor(ORANGE_ACC)
        ax_l.spines["left"].set_edgecolor(BLUE_LOSS)

        if ci == 0:
            ax_l.set_ylabel("Train Loss", color=BLUE_LOSS)
        else:
            ax_l.set_yticklabels([])
            ax_l.set_ylabel("")
        if ci == 1:
            ax_r.set_ylabel("Val Acc (%)", color=ORANGE_ACC)
        else:
            ax_r.set_yticklabels([])

        if ri == 1:
            ax_l.set_xlabel("Epoch")

        ax_l.annotate(
            "epoch 5",
            xy=(5, 0), xycoords=("data", "axes fraction"),
            xytext=(5.5, 0.06), textcoords=("data", "axes fraction"),
            fontsize=7.5, color=GREY_VLINE, va="bottom",
            arrowprops=dict(arrowstyle="-", color=GREY_VLINE, lw=0.6),
        )
        ax_l.annotate(
            f"loss={ep5.train_loss:.3f}",
            xy=(5, ep5.train_loss),
            xytext=(6.5, ep5.train_loss),
            fontsize=7, color=BLUE_LOSS, va="center",
        )
        ax_r.annotate(
            f"acc={ep5.val_acc:.1f}%",
            xy=(5, ep5.val_acc),
            xytext=(6.5, ep5.val_acc - 0.3),
            fontsize=7, color=ORANGE_ACC, va="top",
        )

        ax_l.set_title(f"{seed_label}  |  {aug_label}", pad=5, fontweight="bold")

custom_lines = [
    Line2D([0],[0], color=BLUE_LOSS,  lw=2.0, label="Train Loss"),
    Line2D([0],[0], color=ORANGE_ACC, lw=2.0, label="Val Acc (%)"),
    Line2D([0],[0], color=GREY_VLINE, lw=1.4, linestyle="--", label="Epoch 5 marker"),
]
fig.legend(handles=custom_lines, loc="upper center", ncol=3, fontsize=8.5,
           bbox_to_anchor=(0.5, 1.00), framealpha=0.9)

crossover_note = (
    f"Crossover epoch: {crossover_epoch}" if crossover_epoch is not None
    else "No crossover within 30 epochs (mean gap uniformly negative)"
)
fig.suptitle(
    "Training Dynamics: Loss and Validation Accuracy\n"
    f"Epoch-5 mean gap = {epoch5_mean_gap:+.2f} pp  ·  Regime: "
    f"underfitting-penalty-confirmed  ·  {crossover_note}",
    fontsize=11, y=1.055, fontweight="bold",
)

plt.tight_layout(rect=[0, 0, 1, 0.98])

for ext in ("png", "pdf"):
    out = FIG_DIR / f"fig3_loss_curves.{ext}"
    fig.savefig(str(out), dpi=300, bbox_inches="tight")
    print(f"Saved {out}  ({out.stat().st_size/1024:.1f} KB)")

plt.close(fig)
print("Done.")
'''

with open('scripts/fig3_loss_curves.py', 'w') as fh:
    fh.write(script_final)
print("Final script written to scripts/fig3_loss_curves.py")
