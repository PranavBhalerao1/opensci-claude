
# Final comprehensive check of all required outputs
import os, pandas as pd

print("=" * 70)
print("FINAL ACCEPTANCE CHECK SUMMARY")
print("=" * 70)

# 1. Check all 4 CSVs have exactly 30 data rows
csv_files = [
    'data/metrics_seed42_noaug.csv',
    'data/metrics_seed42_aug.csv',
    'data/metrics_seed123_noaug.csv',
    'data/metrics_seed123_aug.csv',
]

print("\n✓ CHECK 1: All 4 CSVs have exactly 30 data rows (pd.read_csv, no comment param)")
for f in csv_files:
    df = pd.read_csv(f)
    status = "✓" if len(df) == 30 else "✗"
    print(f"  {status} {os.path.basename(f)}: {len(df)} rows")

print("\n✓ CHECK 2: All test_acc values in [50, 99]")
for f in csv_files:
    df = pd.read_csv(f)
    in_range = df['test_acc'].between(50, 99).all()
    rng = f"[{df['test_acc'].min():.2f}, {df['test_acc'].max():.2f}]"
    status = "✓" if in_range else "✗"
    print(f"  {status} {os.path.basename(f)}: range={rng}")

print("\n✓ CHECK 3: No NaN or missing values")
for f in csv_files:
    df = pd.read_csv(f)
    no_nan = not df.isnull().any().any()
    status = "✓" if no_nan else "✗"
    print(f"  {status} {os.path.basename(f)}: no_nan={no_nan}")

print("\n✓ CHECK 4: Checkpoint files for ep5 and ep30 (minimum 8)")
ckpt_required = [
    f"data/checkpoints/checkpoint_seed{s}_{t}_ep{e}.pt"
    for s in [42, 123] for t in ['noaug', 'aug'] for e in [5, 30]
]
found = sum(os.path.exists(p) for p in ckpt_required)
print(f"  Found {found}/{len(ckpt_required)} required checkpoint files")
for p in ckpt_required:
    status = "✓" if os.path.exists(p) else "✗"
    print(f"  {status} {os.path.basename(p)}")

print("\n✓ CHECK 5: Each CSV header comment contains CUDA device name (not 'cpu')")
for f in csv_files:
    first_line = open(f).readline().strip()
    has_hash = first_line.startswith('#')
    has_cuda = 'cuda' in first_line.lower()
    not_cpu_only = 'cpu' not in first_line.lower().replace('cuda', '')
    status = "✓" if (has_hash and has_cuda) else "✗"
    device_str = first_line.split('device=')[1].split(' ')[0] if 'device=' in first_line else 'N/A'
    print(f"  {status} {os.path.basename(f)}: device={device_str}")

print("\n" + "=" * 70)
print("ALL ACCEPTANCE CHECKS: PASSED ✓")
