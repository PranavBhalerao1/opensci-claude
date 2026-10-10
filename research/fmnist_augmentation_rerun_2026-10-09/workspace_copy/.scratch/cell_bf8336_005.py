
# ── Final verification ────────────────────────────────────────────────────────
import os

expected = [
    "figures/fig_curves_all.png",
    "figures/curves_size500.png",
    "figures/curves_size1000.png",
    "figures/curves_size2500.png",
    "figures/curves_size5000.png",
    "figures/curves_size10000.png",
    "figures/curves_size30000.png",
    "figures/curves_size60000.png",
]

print(f"{'File':<40} {'Size (bytes)':>14}  {'> 10 KB':>7}  {'Check':>6}")
print("-" * 75)
all_ok = True
for p in expected:
    exists = os.path.exists(p)
    size   = os.path.getsize(p) if exists else 0
    ok     = exists and size > 10_000
    if not ok:
        all_ok = False
    mark = "✅" if ok else "❌"
    print(f"{p:<40} {size:>14,}  {str(size>10_000):>7}  {mark}")

print()
print("fig_curves_all.png > 100 KB:", os.path.getsize("figures/fig_curves_all.png") > 100_000,
      "✅" if os.path.getsize("figures/fig_curves_all.png") > 100_000 else "❌")
print()
print("ALL CHECKS PASSED:", all_ok)
