
# Run the script
import subprocess, sys
result = subprocess.run(
    [sys.executable, 'scripts/fig3_loss_curves.py'],
    capture_output=True, text=True
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[-2000:] if result.stderr else "")
print("Return code:", result.returncode)
