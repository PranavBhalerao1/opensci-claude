
# Run the probe script to generate the initial environment_report.txt
import subprocess, sys, os

result = subprocess.run(
    [sys.executable, 'scripts/probe_gpu.py'],
    capture_output=True, text=True, cwd=os.getcwd()
)
print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:500])
