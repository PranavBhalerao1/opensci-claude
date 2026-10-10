
import os, pandas as pd, matplotlib, matplotlib.pyplot as plt, matplotlib.patches as mpatches
matplotlib.rcParams['figure.dpi'] = 150

os.makedirs("figures", exist_ok=True)

df = pd.read_csv("analysis/results_all.csv")

SIZES   = [500, 1000, 2500, 5000, 10000, 30000, 60000]
EPOCHS  = [1, 2, 3, 4, 5]
COLORS  = {"noaug": "#1f77b4", "aug": "#ff7f0e"}   # blue / orange
COND_LABELS = {"noaug": "No-Aug", "aug": "Aug"}

def plot_size_panel(ax_loss, ax_acc, df_size, N):
    """Fill two axes (train_loss, val_acc) for one size N."""
    for cond in ["noaug", "aug"]:
        col  = COLORS[cond]
        lbl  = COND_LABELS[cond]
        df_c = df_size[df_size["condition"] == cond]

        # per-seed thin dashed lines
        for seed in [42, 123]:
            df_s = df_c[df_c["seed"] == seed].sort_values("epoch")
            ax_loss.plot(df_s["epoch"], df_s["train_loss"],
                         color=col, lw=0.8, ls="--", alpha=0.55)
            ax_acc.plot(df_s["epoch"], df_s["val_acc"],
                        color=col, lw=0.8, ls="--", alpha=0.55)

        # mean across seeds — thick solid
        grp = df_c.groupby("epoch")[["train_loss", "val_acc"]].mean().reset_index()
        ax_loss.plot(grp["epoch"], grp["train_loss"],
                     color=col, lw=2.2, ls="-", label=lbl)
        ax_acc.plot(grp["epoch"], grp["val_acc"],
                    color=col, lw=2.2, ls="-", label=lbl)

    ax_loss.set_xlabel("Epoch"); ax_loss.set_ylabel("Train Loss")
    ax_loss.set_xticks(EPOCHS)
    ax_loss.set_title(f"Train Loss  (N={N:,})")
    ax_loss.legend(fontsize=8)

    ax_acc.set_xlabel("Epoch"); ax_acc.set_ylabel("Val Accuracy")
    ax_acc.set_xticks(EPOCHS)
    ax_acc.set_title(f"Val Accuracy  (N={N:,})")
    ax_acc.legend(fontsize=8)

# ── per-size individual figures ──────────────────────────────────────────────
for N in SIZES:
    df_N = df[df["size"] == N]
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(10, 4))
    plot_size_panel(ax_l, ax_r, df_N, N)

    # manual legend: dashed thin = individual seeds, solid thick = mean
    handles = [
        mpatches.Patch(color=COLORS["noaug"], label="No-Aug (mean solid, seeds dashed)"),
        mpatches.Patch(color=COLORS["aug"],   label="Aug    (mean solid, seeds dashed)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2,
               fontsize=8, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(f"Fashion-MNIST CNN  |  Training size N={N:,}", fontsize=12, y=1.02)
    fig.tight_layout()
    path = f"figures/curves_size{N}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {path}  ({os.path.getsize(path):,} bytes)")
