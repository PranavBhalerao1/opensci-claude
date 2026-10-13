import subprocess, sys

cmd = [
    sys.executable, "src/train.py",
    "--seed",     "42",
    "--augment",
    "--epochs",   "2",
    "--data_dir", "data/",
    "--out_dir",  "results/smoke_test",
]
print("Running:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
print("=== STDOUT ===")
print(result.stdout)
if result.stderr:
    print("=== STDERR ===")
    print(result.stderr[-3000:])   # tail only
print("Return code:", result.returncode)
