
import os, pandas as pd
import matplotlib, matplotlib.pyplot as plt, matplotlib.patches as mpatches

df = pd.read_csv("analysis/results_all.csv")

SIZES  = [500, 1000, 2500, 5000, 10000, 30000, 60000]
EPOCHS = [1, 2, 3, 4, 5]
COLORS = {"noaug": "#1f77b4", "aug": "#ff7f0e"}
COND_LABELS = {"noaug": "No-Aug", "aug": "Aug"}

def plot_size_panel(ax_loss, ax_acc, df_size, N):
    for cond in ["noaug", "aug"]:
        col = COLORS[cond]
        lbl = COND_LABELS[cond]
        df_c = df_size[df_size["condition"] == cond]
        for seed in [42, 123]:
            df_s = df_c[df_c["seed"] == seed].sort_values("epoch")
            ax_loss.plot(df_s["epoch"], df_s["train_loss"],
                         color=col, lw=0.8, ls="--", alpha=0.55)
            ax_acc.plot(df_s["epoch"], df_s["val_acc"],
                        color=col, lw=0.8, ls="--", alpha=0.55)
        grp = df_c.groupby("epoch")[["train_loss", "val_acc"]].mean().reset_index()
        ax_loss.plot(grp["epoch"], grp["train_loss"],
                     color=col, lw=2.2, ls="-", label=lbl)
        ax_acc.plot(grp["epoch"], grp["val_acc"],
                    color=col, lw=2.2, ls="-", label=lbl)

    ax_loss.set_xlabel("Epoch"); ax_loss.set_ylabel("Train Loss")
    ax_loss.set_xticks(EPOCHS); ax_loss.set_title(f"Train Loss  (N={N:,})")
    ax_loss.legend(fontsize=8)
    ax_acc.set_xlabel("Epoch"); ax_acc.set_ylabel("Val Accuracy")
    ax_acc.set_xticks(EPOCHS); ax_acc.set_title(f"Val Accuracy  (N={N:,})")
    ax_acc.legend(fontsize=8)

# ── combined 7-row × 2-col multi-panel figure ────────────────────────────────
fig, axes = plt.subplots(7, 2, figsize=(12, 28))

for row, N in enumerate(SIZES):
    df_N = df[df["size"] == N]
    ax_l = axes[row, 0]
    ax_r = axes[row, 1]
    plot_size_panel(ax_l, ax_r, df_N, N)
    if row < 6:
        ax_l.set_xlabel("")
        ax_r.set_xlabel("")

handles = [
    mpatches.Patch(color=COLORS["noaug"], label="No-Aug  (mean=solid, seeds=dashed)"),
    mpatches.Patch(color=COLORS["aug"],   label="Aug     (mean=solid, seeds=dashed)"),
]
fig.legend(handles=handles, loc="lower center", ncol=2,
           fontsize=10, bbox_to_anchor=(0.5, 0.0))

fig.suptitle(
    "Fashion-MNIST CNN: Training Loss & Val Accuracy\n"
    "Augmented vs Non-Augmented — All 7 Training Sizes",
    fontsize=14, y=1.005
)
fig.tight_layout(rect=[0, 0.03, 1, 1])

combined_path = "figures/fig_curves_all.png"
fig.savefig(combined_path, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved {combined_path}  ({os.path.getsize(combined_path):,} bytes)")
