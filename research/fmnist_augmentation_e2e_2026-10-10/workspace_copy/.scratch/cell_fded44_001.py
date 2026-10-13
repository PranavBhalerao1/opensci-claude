
import os, pathlib

# Check what files exist
for d in ['analysis', 'figures', 'results', 'scripts']:
    p = pathlib.Path(d)
    if p.exists():
        files = list(p.iterdir())
        print(f"{d}/: {[f.name for f in files]}")
    else:
        print(f"{d}/: MISSING")
