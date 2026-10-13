
import os, json, pathlib

# Check available files
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__']]
    for f in files:
        print(os.path.join(root, f))
