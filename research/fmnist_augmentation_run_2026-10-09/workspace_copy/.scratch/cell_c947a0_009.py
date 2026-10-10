
import subprocess, sys

print("=" * 60)
print("TEST 1: src/model.py self-test")
print("=" * 60)
r = subprocess.run([sys.executable, 'src/model.py'], capture_output=True, text=True)
print(r.stdout)
if r.returncode != 0:
    print("STDERR:", r.stderr[:500])
    raise RuntimeError("model.py self-test failed")
