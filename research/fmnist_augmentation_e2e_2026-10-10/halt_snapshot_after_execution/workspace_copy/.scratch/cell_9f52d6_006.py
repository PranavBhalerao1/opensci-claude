# Now test checkpoint saving by running 5 epochs
import subprocess, sys

cmd = [
    sys.executable, "src/train.py",
    "--seed",     "7",
    "--epochs",   "5",
    "--data_dir", "data/",
    "--out_dir",  "results/smoke_ckpt",
]
print("Running 5-epoch checkpoint test:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-500:])
print("Return code:", result.returncode)
