import subprocess, sys, time

start = time.time()
result = subprocess.run(
    [sys.executable, "src/train.py",
     "--seed", "42",
     "--augment", "false",
     "--epochs", "5",
     "--data_dir", "/tmp/fmnist_smoke",
     "--out_dir", "/tmp/smoke_out"],
    capture_output=True, text=True, timeout=600
)
elapsed = time.time() - start

print("=== STDOUT ===")
print(result.stdout)
if result.stderr:
    print("=== STDERR (last 40 lines) ===")
    print("\n".join(result.stderr.strip().split("\n")[-40:]))
print(f"\nReturn code: {result.returncode}  |  Elapsed: {elapsed:.1f}s")
