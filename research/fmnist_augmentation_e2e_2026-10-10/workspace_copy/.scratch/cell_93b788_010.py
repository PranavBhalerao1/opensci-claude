
# Verify the change was made correctly
with open('src/train.py', 'r') as f:
    content = f.read()

idx1 = content.find('with open(csv_path, "w", newline="")')
idx2 = content.find('Training loop', idx1)
print("Updated CSV setup section:")
print(content[idx1:idx2])
