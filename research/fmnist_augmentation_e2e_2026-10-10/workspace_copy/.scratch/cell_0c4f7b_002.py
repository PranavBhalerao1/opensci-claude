
import os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

# ── Create output directory ────────────────────────────────────────────────
os.makedirs("figures", exist_ok=True)

# ── Load data ──────────────────────────────────────────────────────────────
df = pd.read_csv("analysis/combined_metrics.csv")

# ── Load crossover epoch from upstream artifact ────────────────────────────
crossover_epoch = None
try:
    with open("analysis/crossover_summary.json") as f:
        cs = json.load(f)
    crossover_epoch = cs.get("crossover_epoch", None)
    print("Crossover epoch from JSON:", crossover_epoch)
except FileNotFoundError:
    print("crossover_summary.json not found; skipping crossover marker")

# ── Colour / style map ─────────────────────────────────────────────────────
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

# ── Build figure ───────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))

data_lines = []
for (seed, aug), grp in df.groupby(["seed", "augmented"]):
    grp_sorted = grp.sort_values("epoch")
    style = style_map[(seed, aug)]
    label = label_map[(seed, aug)]
    line, = ax.plot(grp_sorted["epoch"].values,
                    grp_sorted["test_acc"].values,
                    label=label,
                    **style)
    data_lines.append(line)

print(f"Data lines plotted: {len(data_lines)}")
for ln in data_lines:
    print(f"  label={ln.get_label()!r:30s}  color={ln.get_color()}  ls={ln.get_linestyle()}")

# ── Epoch-5 vertical marker ────────────────────────────────────────────────
ax.axvline(x=5, color="grey", linestyle=":", linewidth=1.5, zorder=2)
ax.text(5.2, ax.get_ylim()[0] + 0.5,
        "Epoch-5\ntarget budget",
        fontsize=8, color="grey", va="bottom")

# ── Crossover marker (if applicable) ──────────────────────────────────────
if crossover_epoch is not None and crossover_epoch != "None":
    try:
        ce = int(crossover_epoch)
        ax.axvline(x=ce, color="red", linestyle=":", linewidth=1.3, zorder=2)
        ax.text(ce + 0.2, ax.get_ylim()[0] + 1.8,
                f"Crossover\n(ep {ce})", fontsize=8, color="red", va="bottom")
    except (ValueError, TypeError):
        print("Crossover epoch not an integer; skipping marker")

# ── Labels / title / legend ────────────────────────────────────────────────
ax.set_xlabel("Training Epoch", fontsize=12)
ax.set_ylabel("Test Accuracy (%)", fontsize=12)
ax.set_title("Test Accuracy: Augmented vs Non-Augmented (Fashion-MNIST)", fontsize=13)
ax.set_xlim(1, 30)
ax.xaxis.set_major_locator(plt.MultipleLocator(5))
ax.xaxis.set_minor_locator(plt.MultipleLocator(1))
ax.grid(True, which="major", alpha=0.3)
ax.legend(loc="lower right", fontsize=9, framealpha=0.9)

fig.tight_layout()

# ── Save ───────────────────────────────────────────────────────────────────
png_path = "figures/fig1_test_accuracy_curves.png"
pdf_path = "figures/fig1_test_accuracy_curves.pdf"
fig.savefig(png_path, dpi=300, bbox_inches="tight")
fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
plt.close(fig)

png_size = os.path.getsize(png_path)
pdf_size = os.path.getsize(pdf_path)
print(f"\nSaved PNG: {png_path}  ({png_size:,} bytes)")
print(f"Saved PDF: {pdf_path}  ({pdf_size:,} bytes)")
assert png_size > 20_000, f"PNG too small: {png_size}"
print("✓ PNG size check passed")
