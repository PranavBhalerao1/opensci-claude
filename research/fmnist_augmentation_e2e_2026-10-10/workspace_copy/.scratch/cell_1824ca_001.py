
import os, glob

# Survey workspace
for root, dirs, files in os.walk('.'):
    # Skip hidden dirs
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for f in files:
        path = os.path.join(root, f)
        print(path)
