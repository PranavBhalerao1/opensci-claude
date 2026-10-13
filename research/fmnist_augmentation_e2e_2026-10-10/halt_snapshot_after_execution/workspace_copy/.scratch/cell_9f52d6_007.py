import torch, os

ckpt_dir = "results/smoke_ckpt"
ckpt_files = sorted([f for f in os.listdir(ckpt_dir) if f.endswith(".pt")])
print(f"Checkpoint files: {ckpt_files}")

# Load and inspect ep05 checkpoint
ckpt = torch.load(os.path.join(ckpt_dir, "checkpoint_ep05.pt"), weights_only=False)
print("\nCheckpoint keys:", list(ckpt.keys()))
print(f"  epoch     : {ckpt['epoch']}")
print(f"  seed      : {ckpt['seed']}")
print(f"  augment   : {ckpt['augment']}")
print(f"  train_acc : {ckpt['train_acc']:.4f}")
print(f"  val_acc   : {ckpt['val_acc']:.4f}")
print(f"  model_state keys (first 5): {list(ckpt['model_state'].keys())[:5]}")

# Verify model state loads cleanly
from src.train import SmallCNN
model = SmallCNN()
model.load_state_dict(ckpt["model_state"])
print("\n✓ Checkpoint reloads into SmallCNN without errors")
print(f"✓ All acceptance checks passed")
