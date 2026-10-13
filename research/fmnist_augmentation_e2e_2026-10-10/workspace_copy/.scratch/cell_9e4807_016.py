
# Read GPU log to verify all 4 runs completed
with open('logs/gpu/train_all_runs.log') as f:
    log = f.read()

# Check key markers
for marker in ['RUN 1 COMPLETE', 'RUN 2 COMPLETE', 'RUN 3 COMPLETE', 'RUN 4 COMPLETE',
               'ALL RUNS COMPLETE', 'NVIDIA L4']:
    print(f"  {'✓' if marker in log else '✗'} {marker}")

# Extract final accuracy for each run
import re
finals = re.findall(r'FINAL: epoch-30 test_acc=(\d+\.\d+)%', log)
print(f"\nFinal test_acc values: {finals}")
