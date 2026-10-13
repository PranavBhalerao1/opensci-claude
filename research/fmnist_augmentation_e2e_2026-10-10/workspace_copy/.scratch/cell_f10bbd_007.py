
with open("src/train.py") as f:
    content = f.read()
lines = content.splitlines()

# CSV setup section
for i in range(305, 320):
    print(f"{i+1:4d}: {lines[i]}")
