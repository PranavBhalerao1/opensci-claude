
import subprocess, sys

print("=" * 60)
print("TEST 2: src/train.py smoke test (1 epoch, CPU, random data)")
print("=" * 60)
r = subprocess.run([sys.executable, 'src/train.py'], capture_output=True, text=True)
# Filter out FutureWarnings
stdout_lines = [l for l in r.stdout.split('\n') 
                if 'FutureWarning' not in l and 'pynvml' not in l and 'DeprecationWarning' not in l]
print('\n'.join(stdout_lines))
if r.returncode != 0:
    print("STDERR:", r.stderr[:800])
    raise RuntimeError("train.py smoke test failed")
