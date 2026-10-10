
# Verify the report file content
with open('data/environment_report.txt') as f:
    content = f.read()

print(content)
print("\n--- Acceptance check ---")
has_cuda = 'cuda' in content.lower()
# Check for GPU device name: look for NVIDIA or specific model patterns
gpu_name_present = 'NVIDIA' in content
print(f"Contains 'cuda' (case-insensitive): {has_cuda}")
print(f"Contains 'NVIDIA' (GPU device name): {gpu_name_present}")
print(f"GPU Device Name line: ", [l.strip() for l in content.split('\n') if 'GPU Device Name' in l])
