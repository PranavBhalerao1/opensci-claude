
import os

# Create all required directories
dirs = [
    'src', 'data', 'data/checkpoints', 'data/logs',
    'data/predictions', 'analysis', 'figures', 'tables',
    'results', 'scripts'
]
for d in dirs:
    os.makedirs(d, exist_ok=True)
    
print("Created dirs:")
for d in dirs:
    print(f"  {d}/ -> exists={os.path.isdir(d)}")
