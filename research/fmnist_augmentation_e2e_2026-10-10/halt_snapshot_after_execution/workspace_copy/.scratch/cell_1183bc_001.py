
import os, json, pathlib
import pandas as pd

# Check available files
for root, dirs, files in os.walk('.'):
    # Skip hidden dirs
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for f in files:
        print(os.path.join(root, f))
