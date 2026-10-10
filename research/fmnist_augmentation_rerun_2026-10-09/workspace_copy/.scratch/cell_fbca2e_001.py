
import os
# Check what files exist
for f in ['results/results_seed42.csv', 'results/results_seed123.csv',
          'results/gpu_log_seed42.txt', 'results/gpu_log_seed123.txt']:
    exists = os.path.exists(f)
    print(f"{f}: {'EXISTS' if exists else 'MISSING'}")
