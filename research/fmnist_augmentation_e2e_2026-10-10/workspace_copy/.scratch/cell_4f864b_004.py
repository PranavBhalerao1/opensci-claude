# ── 5. Verify argparse flags exist ──────────────────────────────────────────
import subprocess, sys

result = subprocess.run(
    [sys.executable, "src/train.py", "--help"],
    capture_output=True, text=True
)
print(result.stdout)
for flag in ["--seed", "--augment", "--epochs", "--data_dir", "--out_dir"]:
    assert flag in result.stdout, f"Missing flag: {flag}"
    print(f"  ✓ {flag} present")
