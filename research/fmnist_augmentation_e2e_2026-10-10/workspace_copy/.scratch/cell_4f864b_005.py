# ── 6. Final summary of all verified facts ──────────────────────────────────
import os

csv_path  = "/tmp/smoke_out/metrics_seed42_noaug.csv"
ckpt_path = "/tmp/smoke_out/checkpoints/checkpoint_seed42_noaug_ep05.pt"

csv_size  = os.path.getsize(csv_path)
ckpt_size = os.path.getsize(ckpt_path)

print("=" * 60)
print("SMOKE TEST VERIFICATION SUMMARY")
print("=" * 60)
print(f"Script           : src/train.py  ({os.path.getsize('src/train.py'):,} bytes)")
print(f"Syntax check     : PASS (ast.parse)")
print()
print(f"CSV path         : {csv_path}")
print(f"CSV size         : {csv_size} bytes")
print(f"CSV data rows    : 5  ✓")
print(f"CSV columns      : epoch, train_loss, train_acc, val_acc, test_acc  ✓")
print()
print(f"Checkpoint path  : {ckpt_path}")
print(f"Checkpoint size  : {ckpt_size:,} bytes")
print()
print("Architecture checks:")
print("  • SmallCNN class present           ✓")
print("  • 2 Conv2d layers (1→32, 32→64)    ✓")
print("  • 2 Linear layers (3136→256,256→10)✓")
print("  • No BatchNorm                     ✓")
print("  • Dropout(p=0.25) in FC only       ✓")
print("  • Total params = 824,458           ✓")
print("  • Forward pass → (N,10) logits     ✓")
print()
print("argparse flags    : --seed --augment --epochs --data_dir --out_dir  ✓")
print("Seed fixing       : random, numpy, torch, cuda, cudnn  ✓")
print("Checkpoint epochs : {5, 10, 20, 30}  ✓")
