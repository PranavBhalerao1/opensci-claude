
import os, glob

# Delete stale CSV and checkpoint files from previous failed attempt
# (they must be regenerated from scratch per task requirements)
stale_csvs = glob.glob('data/metrics_seed*.csv')
stale_ckpts = glob.glob('data/checkpoints/checkpoint_seed*.pt')

for f in stale_csvs + stale_ckpts:
    os.remove(f)
    print(f"Deleted: {f}")

print(f"\nDeleted {len(stale_csvs)} CSV files and {len(stale_ckpts)} checkpoint files")
print("Ready to regenerate all outputs via GPU job")
