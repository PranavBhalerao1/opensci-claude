
# Show the full CSV header comment line (line 309 context)
lines = content.splitlines()
for i in range(305, 315):
    print(f"{i+1:4d}: {lines[i]}")
