
import torch, os, glob

print("=" * 60)
print("CHECKPOINT VERIFICATION")
print("=" * 60)

expected_ckpts = []
for seed in [42, 123]:
    for aug in ['noaug', 'aug']:
        for ep in [5, 10, 20, 30]:
            expected_ckpts.append(f"data/checkpoints/checkpoint_seed{seed}_{aug}_ep{ep}.pt")

missing = []
present = []
for path in expected_ckpts:
    if os.path.exists(path):
        present.append(path)
    else:
        missing.append(path)

print(f"Expected: {len(expected_ckpts)} checkpoints")
print(f"Present:  {len(present)}")
print(f"Missing:  {len(missing)}")
if missing:
    print("MISSING:")
    for m in missing:
        print(f"  {m}")

print("\n--- Checkpoint Content Verification (spot check) ---")
for path in ['data/checkpoints/checkpoint_seed42_noaug_ep5.pt',
             'data/checkpoints/checkpoint_seed42_noaug_ep30.pt',
             'data/checkpoints/checkpoint_seed123_aug_ep5.pt',
             'data/checkpoints/checkpoint_seed123_aug_ep30.pt']:
    ckpt = torch.load(path, map_location='cpu')
    size_kb = os.path.getsize(path) / 1024
    print(f"\n  {os.path.basename(path)}")
    print(f"    Size: {size_kb:.1f} KB")
    print(f"    Keys: {sorted(ckpt.keys())}")
    print(f"    epoch={ckpt['epoch']}, seed={ckpt['seed']}, augment={ckpt['augment']}")
    print(f"    test_acc={ckpt['test_acc']:.2f}%")
    # Verify model state_dict can be loaded
    from src.train import SmallCNN
    model = SmallCNN()
    model.load_state_dict(ckpt['model_state'])
    print(f"    Model load: OK")
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"    Params: {n_params:,} (expected 824,458)")

print(f"\n--- All checkpoint sizes ---")
for path in sorted(glob.glob('data/checkpoints/checkpoint_seed*.pt')):
    size_kb = os.path.getsize(path) / 1024
    print(f"  {os.path.basename(path)}: {size_kb:.1f} KB")
