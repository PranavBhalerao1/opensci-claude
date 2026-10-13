
with open('src/train.py', 'r') as f:
    content = f.read()

# Find the CSV setup section and replace it
old_section = '''    with open(csv_path, "w", newline="") as fh:
        fh.write(f"# seed={seed} augment={augment} device={device} "
                 f"start={start_dt}\\n")
        writer = csv.writer(fh)
        writer.writerow(["epoch", "train_loss", "train_acc", "val_a'''

# Find the exact old text
import re
old_pattern = r'    with open\(csv_path, "w", newline=""\) as fh:\n        fh\.write\(f"# seed.*?start=\{start_dt\}\\\\n"\)\n        writer = csv\.writer\(fh\)\n        writer\.writerow\(\["epoch", "train_loss", "train_acc", "val_acc", "test_acc"\]\)'

match = re.search(old_pattern, content, re.DOTALL)
if match:
    print("Found old CSV setup section:")
    print(repr(match.group()))
else:
    print("Pattern not found, trying manual search")
    # Find the section manually
    idx1 = content.find('with open(csv_path, "w", newline="")')
    idx2 = content.find('Training loop', idx1)
    print(repr(content[idx1:idx2]))
