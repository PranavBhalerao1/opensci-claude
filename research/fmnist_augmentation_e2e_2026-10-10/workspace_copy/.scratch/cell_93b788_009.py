
with open('src/train.py', 'r') as f:
    content = f.read()

# Locate and replace the CSV setup section
old_csv_setup = '''    with open(csv_path, "w", newline="") as fh:
        fh.write(f"# seed={seed} augment={augment} device={device} "
                 f"start={start_dt}\\n")
        writer = csv.writer(fh)
        writer.writerow(["epoch", "train_loss", "train_acc", "val_acc", "test_acc"])'''

new_csv_setup = '''    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        # Combine the # comment and column names into ONE header line so that
        # pd.read_csv(path) returns exactly `epochs` data rows (not epochs+1).
        # The first column name IS the comment (starts with "#", contains device).
        comment_col = (f"# seed={seed} augment={augment} "
                       f"device={device} start={start_dt}")
        writer.writerow([comment_col, "train_loss", "train_acc",
                         "val_acc", "test_acc"])'''

if old_csv_setup in content:
    new_content = content.replace(old_csv_setup, new_csv_setup)
    with open('src/train.py', 'w') as f:
        f.write(new_content)
    print("SUCCESS: train.py updated")
else:
    print("FAILED: old section not found. Trying alternative search...")
    print("Looking for 'fh.write' in content:")
    idx = content.find('fh.write(f"# seed')
    print(repr(content[idx-100:idx+200]))
