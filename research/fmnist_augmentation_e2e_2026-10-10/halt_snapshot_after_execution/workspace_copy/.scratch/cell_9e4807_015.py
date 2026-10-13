
import torch, os, glob, sys
sys.path.insert(0, '.')
from src.train import SmallCNN

print("=" * 60)
print("CHECKPOINT CONTENT VERIFICATION")
print("=" * 60)

spot_check = [
    'data/checkpoints/checkpoint_seed42_noaug_ep5.pt',
    'data/checkpoints/checkpoint_seed42_noaug_ep30.pt',
    'data/checkpoints/checkpoint_seed42_aug_ep5.pt',
    'data/checkpoints/checkpoint_seed42_aug_ep30.pt',
    'data/checkpoints/checkpoint_seed123_noaug_ep5.pt',
    'data/checkpoints/checkpoint_seed123_noaug_ep30.pt',
    'data/checkpoints/checkpoint_seed123_aug_ep5.pt',
    'data/checkpoints/checkpoint_seed123_aug_ep30.pt',
]

for path in spot_check:
    ckpt = torch.load(path, map_location='cpu', weights_only=False)
    size_kb = os.path.getsize(path) / 1024
    model = SmallCNN()
    model.load_state_dict(ckpt['model_state'])
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"{os.path.basename(path):50s}  {size_kb:8.1f}KB  "
          f"epoch={ckpt['epoch']}  seed={ckpt['seed']}  aug={ckpt['augment']}  "
          f"test_acc={ckpt['test_acc']:.2f}%  params={n_params:,}")

print(f"\nAll 8 ep5/ep30 checkpoints verified OK")

# Verify all 16
total = 0
for path in sorted(glob.glob('data/checkpoints/checkpoint_seed*.pt')):
    total += 1
print(f"Total checkpoint files: {total}/16 {'OK' if total==16 else 'FAIL'}")
