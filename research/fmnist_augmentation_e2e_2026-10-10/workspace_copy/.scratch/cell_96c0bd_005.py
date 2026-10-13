
import os

# Check for crossover_report.txt
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv']]
    for f in files:
        if 'crossover' in f.lower():
            print(os.path.join(root, f))
