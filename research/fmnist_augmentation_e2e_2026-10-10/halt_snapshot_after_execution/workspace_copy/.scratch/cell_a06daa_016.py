
import os, re

path = "analysis/crossover_report.txt"
size = os.path.getsize(path)
print(f"File size: {size} bytes  (non-empty: {size > 0})")

with open(path) as f:
    content = f.read()

# Acceptance check 1: file exists and is non-empty
print(f"\n[CHECK 1] File exists and non-empty: {size > 0}")

# Acceptance check 2: contains epoch-5 gap values for both seeds
has_ep5_s42  = "-2.1500" in content or "-2.15" in content
has_ep5_s123 = "-3.2500" in content or "-3.25" in content
print(f"[CHECK 2] Contains epoch-5 gap_seed42:  {has_ep5_s42}")
print(f"[CHECK 2] Contains epoch-5 gap_seed123: {has_ep5_s123}")

# Acceptance check 3: contains a regime classification string
for regime in ["underfitting-penalty-confirmed", "early-benefit", "mixed"]:
    if regime in content:
        print(f"[CHECK 3] Regime classification found: '{regime}'")
        break
else:
    print("[CHECK 3] FAIL: No regime classification string found")

# Acceptance check 4: contains crossover statement
if "No crossover within 30 epochs" in content:
    print("[CHECK 4] Crossover statement: 'No crossover within 30 epochs'")
elif re.search(r"Crossover at epoch \d+", content):
    m = re.search(r"Crossover at epoch (\d+)", content)
    print(f"[CHECK 4] Crossover statement: 'Crossover at epoch {m.group(1)}'")
else:
    print("[CHECK 4] FAIL: No crossover statement found")

# Acceptance check 5: traceable numbers
# Sample spot checks
numbers_to_trace = [
    ("-2.1500", "gap_seed42 ep5"),
    ("-3.2500", "gap_seed123 ep5"),
    ("-2.7000", "mean_gap ep5"),
    ("-1.9250", "mean_gap ep10"),
    ("-1.5750", "mean_gap ep20"),
    ("-1.3150", "mean_gap ep30"),
    ("0.187928", "noaug_s42 train_loss ep5"),
    ("0.376089", "aug_s42 train_loss ep5"),
    ("91.30",    "noaug_s42 test_acc ep5"),
    ("89.15",    "aug_s42 test_acc ep5"),
    ("0.051005", "noaug_s42 train_loss ep30"),
    ("92.65",    "noaug_s42 test_acc ep30"),
]
print("\n[CHECK 5] Traceability of numeric values:")
all_traceable = True
for num, label in numbers_to_trace:
    found = num in content
    if not found:
        all_traceable = False
    print(f"  {'OK' if found else 'MISSING'} {num:12s}  ({label})")
print(f"  All traceable: {all_traceable}")
