
with open('src/train.py', 'r') as f:
    content = f.read()

# Check all write operations in main
import re
writes = [(m.start(), content[max(0,m.start()-200):m.start()+200]) 
          for m in re.finditer(r'writer\.writerow|fh\.write', content)]
print(f"Total write calls: {len(writes)}")
for i, (pos, ctx) in enumerate(writes):
    print(f"\n--- Write #{i+1} at char {pos} ---")
    print(ctx)
