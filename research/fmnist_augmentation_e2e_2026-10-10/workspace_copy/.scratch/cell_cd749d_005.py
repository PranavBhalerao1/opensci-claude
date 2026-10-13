
# Final acceptance check: confirm file exists and contains 'PASS'
import pathlib

p = pathlib.Path("data/run_checks/seed42_aug_verified.txt")
text = p.read_text()

print("File exists:", p.exists())
print("Contains 'PASS':", "PASS" in text)
print("Contains 'FAIL':", "FAIL" in text)          # should be False (no FAIL flags)
print("Contains epoch-5 test_acc '89.15':", "89.15" in text)
