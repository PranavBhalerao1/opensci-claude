
import os, torch

print("=" * 65)
print("STEP 2 (corrected): Verify all 16 checkpoint files")
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
all_ok = True

for (seed_str, aug_tag) in conditions:
    for ep in epochs:
        fname = f"checkpoint_{seed_str}_{aug_tag}_ep{ep}.pt"
        fpath = f"data/checkpoints/{fname}"

        exists = os.path.exists(fpath)
        if not exists:
            missing.append(fpath)
            print(f"  ✗ MISSING: {fpath}")
            all_ok = False
            continue

        size_mb = os.path.getsize(fpath) / 1e6

        try:
            ckpt = torch.load(fpath, map_location="cpu", weights_only=False)
            keys = list(ckpt.keys())
            
            # The checkpoint uses 'model_state' key
            state_key = "model_state" if "model_state" in ckpt else \
                        "model_state_dict" if "model_state_dict" in ckpt else None

            has_epoch   = "epoch" in ckpt
            has_state   = state_key is not None
            epoch_match = ckpt.get("epoch") == ep
            n_layers    = len(ckpt[state_key]) if has_state else 0
            seed_val    = ckpt.get("seed")
            aug_val     = ckpt.get("augment")

            # Verify model_state shapes are correct
            if has_state and n_layers > 0:
                state = ckpt[state_key]
                # Check key layer shapes
                conv1_w = state.get("conv1.weight", None)
                fc2_w   = state.get("fc2.weight", None)
                shapes_ok = (conv1_w is not None and conv1_w.shape == (32, 1, 3, 3) and
                             fc2_w   is not None and fc2_w.shape   == (10, 256))
            else:
                shapes_ok = False

            ok = has_epoch and has_state and epoch_match and shapes_ok
            status = "✓" if ok else "✗"
            if not ok:
                all_ok = False
                corrupt.append(fpath)

            print(f"  {status} {fname:46s}  {size_mb:.1f}MB  "
                  f"epoch={ckpt.get('epoch')} seed={seed_val} aug={aug_val}  "
                  f"layers={n_layers}  shapes={'✓' if shapes_ok else '✗'}")

        except Exception as e:
            print(f"  ✗ LOAD ERROR: {fpath}  ({e})")
            corrupt.append(fpath)
            all_ok = False

print(f"\n{'='*65}")
total = len(conditions) * len(epochs)
ok_count = total - len(missing) - len(corrupt)
print(f"Checkpoints: {ok_count}/{total} OK  |  {len(missing)} missing  |  {len(corrupt)} corrupt")
print(f"Overall checkpoint result: {'ALL PASS ✓' if all_ok else 'FAILURES DETECTED ✗'}")
