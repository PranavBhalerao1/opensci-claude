
import os, pathlib

# Check what's available
for p in ['analysis/gap_trajectory.csv', 'analysis/crossover_report.txt',
          'analysis/checkpoint_stats.csv', 'analysis/combined_metrics.csv']:
    exists = os.path.exists(p)
    size   = os.path.getsize(p) if exists else 0
    print(f"{p}: exists={exists}, size={size}")
