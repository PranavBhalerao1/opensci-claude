
import os

# Create src/__init__.py
with open('src/__init__.py', 'w') as f:
    f.write('# Fashion-MNIST SmallCNN study — source package\n')

# Clean up leftover smoke test artifacts from previous run
stale = [
    'data/checkpoints/smoke_test_epoch0001.pt',
    'data/checkpoints/smoke_test_summary.json',
    'data/logs/smoke_test_log.csv',
]
for path in stale:
    if os.path.exists(path):
        os.remove(path)
        print(f"Removed stale: {path}")

print("src/__init__.py created:", os.path.exists('src/__init__.py'))
