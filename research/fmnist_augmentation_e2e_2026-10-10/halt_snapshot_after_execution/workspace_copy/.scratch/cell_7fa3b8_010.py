
# Check for any fig2-related scripts or files
import os, glob

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for f in files:
        if 'fig2' in f.lower() or 'gap_traj' in f.lower():
            print(os.path.join(root, f))

# Check scripts
for f in os.listdir('scripts'):
    print('scripts/', f)
