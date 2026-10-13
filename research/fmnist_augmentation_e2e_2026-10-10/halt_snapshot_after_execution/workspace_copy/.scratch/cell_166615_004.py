
# Final sanity-check: confirm the file exists and contains 'PASS'
import pathlib
p = pathlib.Path("data/run_checks/seed123_aug_verified.txt")
content = p.read_text()
print("File exists:", p.exists())
print("Contains 'PASS':", "PASS" in content)
print("File size (bytes):", p.stat().st_size)
