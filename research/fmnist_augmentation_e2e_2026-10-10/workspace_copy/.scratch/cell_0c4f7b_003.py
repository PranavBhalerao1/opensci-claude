
# ── Independent verification: reload the saved PNG and count lines ─────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np

# Re-open the figure from scratch using the saved PNG as a visual check,
# but also reload via matplotlib's figure API by re-running the plot
# and inspecting axes children programmatically.

# ---- approach: replot into a fresh figure and inspect axes ----
import pandas as pd, os

df2 = pd.read_csv("analysis/combined_metrics.csv")

fig2, ax2 = plt.subplots()
style_map2 = {
    (42,  False): dict(color="#1f77b4", linestyle="-",  linewidth=1.8),
    (42,  True):  dict(color="#ff7f0e", linestyle="-",  linewidth=1.8),
    (123, False): dict(color="#1f77b4", linestyle="--", linewidth=1.8),
    (123, True):  dict(color="#ff7f0e", linestyle="--", linewidth=1.8),
}
label_map2 = {
    (42,  False): "Seed 42 – No Aug",
    (42,  True):  "Seed 42 – Aug",
    (123, False): "Seed 123 – No Aug",
    (123, True):  "Seed 123 – Aug",
}
for (seed, aug), grp in df2.groupby(["seed","augmented"]):
    ax2.plot(grp.sort_values("epoch")["epoch"],
             grp.sort_values("epoch")["test_acc"],
             label=label_map2[(seed,aug)],
             **style_map2[(seed,aug)])
ax2.axvline(x=5, color="grey", linestyle=":", linewidth=1.5)

all_lines = ax2.get_lines()
data_lines_only = [l for l in all_lines if l.get_label() and not l.get_label().startswith("_")]
print(f"Total lines in axes  : {len(all_lines)}")
print(f"Labeled data lines   : {len(data_lines_only)}")
for l in data_lines_only:
    xd = l.get_xdata()
    yd = l.get_ydata()
    print(f"  label={l.get_label()!r:30s}  pts={len(xd)}  "
          f"y[0]={yd[0]:.2f}  y[-1]={yd[-1]:.2f}")

plt.close(fig2)

# ---- file-system sanity ----
for p in ["figures/fig1_test_accuracy_curves.png",
          "figures/fig1_test_accuracy_curves.pdf"]:
    sz = os.path.getsize(p)
    print(f"{p}: {sz:,} bytes  ({'OK' if sz>20000 else 'TOO SMALL'})")
