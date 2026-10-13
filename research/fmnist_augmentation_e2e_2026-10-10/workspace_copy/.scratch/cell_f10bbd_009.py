
import os, torch

print("=" * 65)
print("STEP 2: Verify all 16 checkpoint files")
print("=" * 65)

conditions = [
    ("seed42",  "noaug"),
    ("seed42",  "aug"),
    ("seed123", "noaug"),
    ("seed123", "aug"),
]
epochs = [5, 10, 20, 30]

missing = []
corrupt = []

for (seed_str, aug_tag) in conditions:
    for ep in epochs:
        fname = f"checkpoint_{seed_str}_{aug_tag}_ep{ep}.pt"
        fpath = f"data/checkpoints/{fname}"
        
        exists = os.path.exists(fpath)
        if not exists:
            missing.append(fpath)
            print(f"  ✗ MISSING: {fpath}")
            continue
        
        size_mb = os.path.getsize(fpath) / 1e6
        
        # Try loading and verifying contents
        try:
            ckpt = torch.load(fpath, map_location="cpu", weights_only=False)
            has_epoch   = "epoch"    in ckpt
            has_state   = "model_state_dict" in ckpt
            epoch_match = ckpt.get("epoch") == ep
            seed_val    = ckpt.get("seed")
            aug_val     = ckpt.get("augment")
            n_layers    = len(ckpt["model_state_dict"]) if has_state else 0
            status = "✓" if (has_epoch and has_state and epoch_match) else "✗"
            print(f"  {status} {fname:48s}  {size_mb:.1f}MB  "
                  f"epoch={ckpt.get('epoch')} seed={seed_val} aug={aug_val}  "
                  f"layers={n_layers}")
            if status == "✗":
                corrupt.append(fpath)
        except Exception as e:
            print(f"  ✗ LOAD ERROR: {fpath}  ({e})")
            corrupt.append(fpath)

print(f"\n{'='*65}")
total = len(conditions) * len(epochs)
ok = total - len(missing) - len(corrupt)
print(f"Checkpoints: {ok}/{total} OK,  {len(missing)} missing,  {len(corrupt)} corrupt")
