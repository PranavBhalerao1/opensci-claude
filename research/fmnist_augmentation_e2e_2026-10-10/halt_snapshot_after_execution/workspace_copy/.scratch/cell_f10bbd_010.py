
import torch

# Inspect one checkpoint in detail
ckpt = torch.load("data/checkpoints/checkpoint_seed42_noaug_ep5.pt", 
                   map_location="cpu", weights_only=False)

print("Top-level keys:", list(ckpt.keys()))
print()

for k, v in ckpt.items():
    if isinstance(v, dict):
        print(f"  {k} (dict with {len(v)} sub-keys):")
        for sk in list(v.keys())[:8]:
            sv = v[sk]
            if hasattr(sv, 'shape'):
                print(f"    {sk}: {sv.shape} {sv.dtype}")
            else:
                print(f"    {sk}: {sv}")
    elif hasattr(v, 'shape'):
        print(f"  {k}: tensor {v.shape}")
    else:
        print(f"  {k}: {v}")
