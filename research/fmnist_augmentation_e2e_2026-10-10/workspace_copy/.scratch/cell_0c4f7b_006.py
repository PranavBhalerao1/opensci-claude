
# Final file-system check
import os

files = {
    "figures/fig1_test_accuracy_curves.png": 20_000,
    "figures/fig1_test_accuracy_curves.pdf": 0,
    "figures/fig1_verification.json":        0,
    "scripts/plot_fig1.py":                  0,
}
all_ok = True
for path, min_size in files.items():
    sz = os.path.getsize(path)
    status = "✓" if sz > min_size else "✗"
    if sz <= min_size:
        all_ok = False
    print(f"{status} {path}: {sz:,} bytes (min {min_size:,})")

print("\nAll checks passed:", all_ok)
