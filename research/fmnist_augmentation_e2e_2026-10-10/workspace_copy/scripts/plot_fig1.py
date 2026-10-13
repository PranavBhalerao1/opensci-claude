"""
scripts/plot_fig1.py
====================
Standalone, independently runnable script that:
  1. Reads  analysis/combined_metrics.csv
  2. Produces figures/fig1_test_accuracy_curves.{png,pdf}
  3. Prints / writes figures/fig1_verification.json with line-count evidence

Usage:
    python scripts/plot_fig1.py

Provenance:
  - Input : analysis/combined_metrics.csv  (task T3.1)
  - Output: figures/fig1_test_accuracy_curves.png (.pdf)
  - Date  : 2026-10-10
"""

import os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Directories ──────────────────────────────────────────────────────────────
os.makedirs("figures", exist_ok=True)

# ── Data ─────────────────────────────────────────────────────────────────────
df = pd.read_csv("analysis/combined_metrics.csv")
assert df.shape == (120, 6), f"Unexpected shape: {df.shape}"
groups = df.groupby(["seed","augmented"]).size().to_dict()
assert len(groups) == 4, f"Expected 4 groups, got {groups}"

# ── Style map ─────────────────────────────────────────────────────────────────
BLUE   = "#1f77b4"
ORANGE = "#ff7f0e"

style_map = {
    (42,  False): dict(color=BLUE,   linestyle="-",  linewidth=1.8),
    (42,  True):  dict(color=ORANGE, linestyle="-",  linewidth=1.8),
    (123, False): dict(color=BLUE,   linestyle="--", linewidth=1.8),
    (123, True):  dict(color=ORANGE, linestyle="--", linewidth=1.8),
}
label_map = {
    (42,  False): "Seed 42 – No Aug",
    (42,  True):  "Seed 42 – Aug",
    (123, False): "Seed 123 – No Aug",
    (123, True):  "Seed 123 – Aug",
}

# ── Figure ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))

data_lines = []
for (seed, aug), grp in df.groupby(["seed", "augmented"]):
    grp_sorted = grp.sort_values("epoch")
    line, = ax.plot(
        grp_sorted["epoch"].values,
        grp_sorted["test_acc"].values,
        label=label_map[(seed, aug)],
        **style_map[(seed, aug)],
    )
    data_lines.append(line)

# Epoch-5 vertical marker
ax.axvline(x=5, color="grey", linestyle=":", linewidth=1.5, zorder=2)
ax.text(5.2, ax.get_ylim()[0] + 0.5,
        "Epoch-5\ntarget budget",
        fontsize=8, color="grey", va="bottom")

ax.set_xlabel("Training Epoch", fontsize=12)
ax.set_ylabel("Test Accuracy (%)", fontsize=12)
ax.set_title("Test Accuracy: Augmented vs Non-Augmented (Fashion-MNIST)", fontsize=13)
ax.set_xlim(1, 30)
ax.xaxis.set_major_locator(plt.MultipleLocator(5))
ax.xaxis.set_minor_locator(plt.MultipleLocator(1))
ax.grid(True, which="major", alpha=0.3)
ax.legend(loc="lower right", fontsize=9, framealpha=0.9)

fig.tight_layout()

# ── Save ─────────────────────────────────────────────────────────────────────
png_path = "figures/fig1_test_accuracy_curves.png"
pdf_path = "figures/fig1_test_accuracy_curves.pdf"
fig.savefig(png_path, dpi=300, bbox_inches="tight")
fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
plt.close(fig)

# ── Verification ─────────────────────────────────────────────────────────────
all_axes_lines = ax.get_lines()  # collected before close – same object
labeled = [l for l in data_lines]   # the 4 we plotted

print(f"Total axes lines    : {len(all_axes_lines)}")  # 5 (4 data + 1 vline)
print(f"Labeled data lines  : {len(labeled)}")         # 4
for ln in labeled:
    yd = ln.get_ydata()
    print(f"  {ln.get_label()!r:30s}  color={ln.get_color()}  "
          f"ls={ln.get_linestyle()!r}  pts={len(yd)}  "
          f"y[0]={yd[0]:.2f}  y[-1]={yd[-1]:.2f}")

verification = {
    "figure": png_path,
    "total_axes_lines": len(all_axes_lines),
    "labeled_data_lines": len(labeled),
    "lines": [
        {
            "label":     ln.get_label(),
            "color":     ln.get_color(),
            "linestyle": "solid" if ln.get_linestyle() in ("-", "solid") else "dashed",
            "n_points":  len(ln.get_ydata()),
        }
        for ln in labeled
    ],
    "vertical_marker_epoch": 5,
    "png_bytes": os.path.getsize(png_path),
    "pdf_bytes": os.path.getsize(pdf_path),
}
with open("figures/fig1_verification.json", "w") as f:
    json.dump(verification, f, indent=2)

print(f"\nPNG: {png_path}  ({verification['png_bytes']:,} bytes)")
print(f"PDF: {pdf_path}  ({verification['pdf_bytes']:,} bytes)")
assert verification["png_bytes"] > 20_000, "PNG too small!"
assert len(labeled) == 4, "Expected 4 data lines!"
print("\n✓ All checks passed.")
