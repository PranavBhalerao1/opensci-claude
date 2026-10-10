
# ── combined 7-row × 2-col multi-panel figure ────────────────────────────────
fig, axes = plt.subplots(7, 2, figsize=(12, 28))

for row, N in enumerate(SIZES):
    df_N   = df[df["size"] == N]
    ax_l   = axes[row, 0]
    ax_r   = axes[row, 1]
    plot_size_panel(ax_l, ax_r, df_N, N)
    # clean up inner tick labels to save space
    if row < 6:
        ax_l.set_xlabel("")
        ax_r.set_xlabel("")

# unified legend below the whole figure
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
