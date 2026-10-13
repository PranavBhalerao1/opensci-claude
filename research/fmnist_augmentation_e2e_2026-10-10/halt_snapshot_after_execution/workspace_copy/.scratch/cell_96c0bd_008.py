
# Write the plotting script to scripts/
script = r'''#!/usr/bin/env python3
"""
fig3_loss_curves.py
===================
Produce fig3_loss_curves.png and fig3_loss_curves.pdf:
  2×2 subplot grid (rows=seeds, columns=conditions) with
  train_loss (left/blue y-axis) and val_acc (right/orange y-axis),
  plus a vertical epoch-5 marker in each panel.

Provenance:
  Input : analysis/combined_metrics.csv  (T3.1 output, accessed 2026-10-10)
  Output: figures/fig3_loss_curves.{png,pdf}
"""
import json, pathlib
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

# ── paths ────────────────────────────────────────────────────────────────────
ROOT        = pathlib.Path(__file__).resolve().parent.parent
CSV_PATH    = ROOT / "analysis" / "combined_metrics.csv"
JSON_PATH   = ROOT / "analysis" / "crossover_summary.json"
FIG_DIR     = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

# ── load data ─────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)
assert df.shape == (120, 6), f"Unexpected shape: {df.shape}"

with open(JSON_PATH) as fh:
    crossover = json.load(fh)

crossover_epoch  = crossover["crossover_epoch"]   # None = never crossed over
epoch5_mean_gap  = crossover["epoch5_mean_gap_pp"]

# ── style constants ──────────────────────────────────────────────────────────
BLUE_LOSS  = "#2166AC"     # blue  → train_loss
ORANGE_ACC = "#D6604D"     # orange/red → val_acc
GREY_VLINE = "#808080"
EPOCH5_LW  = 1.4

CONDITIONS = [
    (False, "No Augmentation"),
    (True,  "Augmentation"),
]
SEEDS = [
    (42,  "Seed 42"),
    (123, "Seed 123"),
]

plt.rcParams.update({
    "font.family"      : "DejaVu Sans",
    "font.size"        : 10,
    "axes.titlesize"   : 10,
    "axes.labelsize"   : 9,
    "xtick.labelsize"  : 8,
    "ytick.labelsize"  : 8,
    "axes.spines.top"  : False,
    "figure.dpi"       : 150,
})

# ── build figure ─────────────────────────────────────────────────────────────
fig, axes = plt.subplots(
    nrows=2, ncols=2,
    figsize=(10, 7),
    sharex=True,
)

for row_idx, (seed, seed_label) in enumerate(SEEDS):
    for col_idx, (aug_flag, aug_label) in enumerate(CONDITIONS):

        ax_l = axes[row_idx, col_idx]          # left axis  → train_loss
        ax_r = ax_l.twinx()                    # right axis → val_acc

        mask = (df["seed"] == seed) & (df["augmented"] == aug_flag)
        sub  = df[mask].sort_values("epoch")

        epochs     = sub["epoch"].values
        train_loss = sub["train_loss"].values
        val_acc    = sub["val_acc"].values

        # ── plot lines ───────────────────────────────────────────────────────
        loss_line, = ax_l.plot(epochs, train_loss,
                               color=BLUE_LOSS,  lw=2.0, zorder=3,
                               label="train_loss")
        acc_line,  = ax_r.plot(epochs, val_acc,
                               color=ORANGE_ACC, lw=2.0, zorder=3,
                               label="val_acc")

        # ── epoch-5 vertical marker ──────────────────────────────────────────
        ax_l.axvline(x=5, color=GREY_VLINE, linestyle="--",
                     lw=EPOCH5_LW, alpha=0.85, zorder=2, label="Epoch 5")
        ax_l.text(5.25, ax_l.get_ylim()[1] * 0.98 if ax_l.get_ylim()[1] != 1
                  else 0.98,
                  "ep 5", color=GREY_VLINE, fontsize=7.5, va="top")

        # ── crossover epoch marker (if exists) ───────────────────────────────
        if crossover_epoch is not None:
            ax_l.axvline(x=crossover_epoch, color="purple", linestyle=":",
                         lw=1.2, alpha=0.8, zorder=2)
            ax_l.text(crossover_epoch + 0.25, ax_l.get_ylim()[0],
                      f"xover\nep{crossover_epoch}", color="purple",
                      fontsize=7, va="bottom")

        # ── axes formatting ──────────────────────────────────────────────────
        ax_l.set_xlim(1, 30)
        ax_l.xaxis.set_major_locator(ticker.MultipleLocator(5))
        ax_l.xaxis.set_minor_locator(ticker.MultipleLocator(1))

        ax_l.tick_params(axis="x", which="both", direction="in")
        ax_l.tick_params(axis="y", colors=BLUE_LOSS)
        ax_r.tick_params(axis="y", colors=ORANGE_ACC)
        ax_r.spines["right"].set_edgecolor(ORANGE_ACC)
        ax_l.spines["left"].set_edgecolor(BLUE_LOSS)

        # y-axis labels only on edge subplots
        if col_idx == 0:
            ax_l.set_ylabel("Train Loss", color=BLUE_LOSS)
        if col_idx == 1:
            ax_r.set_ylabel("Val Acc (%)", color=ORANGE_ACC)

        if row_idx == 1:
            ax_l.set_xlabel("Epoch")

        # ── per-subplot title ────────────────────────────────────────────────
        ax_l.set_title(f"{seed_label} | {aug_label}", pad=4)

        # ── legend (first subplot only to avoid clutter) ─────────────────────
        if row_idx == 0 and col_idx == 0:
            custom_lines = [
                Line2D([0], [0], color=BLUE_LOSS,  lw=2.0, label="Train Loss"),
                Line2D([0], [0], color=ORANGE_ACC, lw=2.0, label="Val Acc (%)"),
                Line2D([0], [0], color=GREY_VLINE, lw=EPOCH5_LW,
                       linestyle="--", label="Epoch 5 marker"),
            ]
            if crossover_epoch is not None:
                custom_lines.append(
                    Line2D([0], [0], color="purple", lw=1.2,
                           linestyle=":", label=f"Crossover ep{crossover_epoch}")
                )
            ax_l.legend(handles=custom_lines, fontsize=7.5,
                        loc="upper right", framealpha=0.7)

        # ── epoch-5 gap annotation ────────────────────────────────────────────
        ep5_row = sub[sub["epoch"] == 5]
        if not ep5_row.empty:
            ep5_loss = ep5_row["train_loss"].values[0]
            ep5_acc  = ep5_row["val_acc"].values[0]
            # small dot on each curve at epoch 5
            ax_l.scatter([5], [ep5_loss], color=BLUE_LOSS,  s=28, zorder=5)
            ax_r.scatter([5], [ep5_acc],  color=ORANGE_ACC, s=28, zorder=5)

# ── epoch-5 text label – re-render after axis limits are set ────────────────
# (Overwrite the placeholder text above with correct y position)
for row_idx, (seed, _) in enumerate(SEEDS):
    for col_idx, (aug_flag, _) in enumerate(CONDITIONS):
        ax = axes[row_idx, col_idx]
        ymin, ymax = ax.get_ylim()
        # remove old text and re-add at correct y
        for txt in ax.texts:
            if txt.get_text().startswith("ep 5"):
                txt.set_y(ymax - (ymax - ymin) * 0.02)

# ── super-title ───────────────────────────────────────────────────────────────
crossover_note = (
    f"Crossover epoch: {crossover_epoch}"
    if crossover_epoch is not None
    else "No crossover within 30 epochs (gap uniformly negative)"
)
fig.suptitle(
    f"Training Dynamics: Loss and Validation Accuracy\n"
    f"Epoch-5 mean gap = {epoch5_mean_gap:+.2f} pp  |  {crossover_note}",
    fontsize=12, y=1.01, fontweight="bold"
)

plt.tight_layout(rect=[0, 0, 1, 1])

# ── save ──────────────────────────────────────────────────────────────────────
for ext in ("png", "pdf"):
    out = FIG_DIR / f"fig3_loss_curves.{ext}"
    fig.savefig(str(out), dpi=300, bbox_inches="tight")
    print(f"Saved {out}  ({out.stat().st_size/1024:.1f} KB)")

plt.close(fig)
print("Done.")
'''

with open('scripts/fig3_loss_curves.py', 'w') as fh:
    fh.write(script)
print("Script written.")
