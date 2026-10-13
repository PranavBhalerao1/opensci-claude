import os

print("=== Produced files ===")
for root, dirs, files in os.walk("."):
    # Skip hidden dirs, data, __pycache__, .venv
    dirs[:] = [d for d in dirs if not d.startswith(".") 
               and d not in ("__pycache__", ".venv", "FashionMNIST")]
    for fn in files:
        path = os.path.join(root, fn)
        size = os.path.getsize(path)
        print(f"  {path:55s}  {size:>8,} bytes")
