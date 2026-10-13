
import os, torch

print("=" * 60)
print("VERIFICATION: All 16 Checkpoint Files")
print("=" * 60)

checkpoint_epochs = [5, 10, 20, 30]
conditions = [
    (42,  'noaug'),
    (42,  'aug'),
    (123, 'noaug'),
    (123, 'aug'),
]

all_ckpts_ok = True
for seed, aug_tag in conditions:
    print(f"\n--- seed={seed}, {aug_tag} ---")
    for ep in checkpoint_epochs:
        fname = f"data/checkpoints/checkpoint_seed{seed}_{aug_tag}_ep{ep}.pt"
        exists = os.path.exists(fname)
        if exists:
            size_kb = os.path.getsize(fname) / 1024
            ckpt = torch.load(fname, map_location='cpu', weights_only=True)
            fields_ok = all(k in ckpt for k in ['epoch', 'seed', 'augment', 'model_state'])
            epoch_match = ckpt['epoch'] == ep
            seed_match  = ckpt['seed']  == seed
            aug_match   = ckpt['augment'] == (aug_tag == 'aug')
            test_acc    = ckpt.get('test_acc', 'N/A')
            ok = exists and fields_ok and epoch_match and seed_match and aug_match
            if not ok:
                all_ckpts_ok = False
            status = '✓' if ok else '✗ FAIL'
            print(f"  ep{ep:2d}: {size_kb:.0f}KB  epoch={ckpt['epoch']} seed={ckpt['seed']} "
                  f"aug={ckpt['augment']} test_acc={test_acc:.2f}% {status}")
        else:
            print(f"  ep{ep:2d}: MISSING ✗ FAIL")
            all_ckpts_ok = False

print(f"\n{'='*60}")
print(f"All checkpoint checks passed: {all_ckpts_ok}")
