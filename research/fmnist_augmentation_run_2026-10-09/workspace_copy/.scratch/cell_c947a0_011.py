
import os

print("=== Checkpoint files ===")
for f in os.listdir('data/checkpoints'):
    path = os.path.join('data/checkpoints', f)
    print(f"  {f}  ({os.path.getsize(path):,} bytes)")

print("\n=== Log files ===")
for f in os.listdir('data/logs'):
    path = os.path.join('data/logs', f)
    with open(path) as fh:
        print(f"  {f}:")
        print("  " + fh.read().strip())

print("\n=== Directories ===")
required_dirs = ['src', 'data', 'data/checkpoints', 'data/logs',
                 'data/predictions', 'analysis', 'figures', 'tables',
                 'results', 'scripts']
for d in required_dirs:
    exists = os.path.isdir(d)
    print(f"  {d}/  {'OK' if exists else 'MISSING'}")
