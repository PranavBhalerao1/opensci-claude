
# Regenerate environment_report.txt using the updated probe script
import subprocess, sys, os

result = subprocess.run(
    [sys.executable, 'scripts/probe_gpu.py'],
    capture_output=True, text=True, cwd=os.getcwd()
)
# Filter warnings
lines = [l for l in result.stdout.split('\n')
         if 'FutureWarning' not in l and 'pynvml' not in l and 'DeprecationWarning' not in l]
print('\n'.join(lines))
if result.returncode != 0:
    print("STDERR:", result.stderr[:500])
