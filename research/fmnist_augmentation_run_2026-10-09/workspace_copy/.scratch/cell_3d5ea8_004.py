
import sys
sys.path.insert(0, ".")

from src.train import run_training

smoke_config = {
    "run_name"    : "smoke_test",
    "seed"        : 42,
    "num_epochs"  : 1,
    "lr"          : 1e-3,
    "batch_size"  : 256,
    "weight_decay": 1e-4,
    "augment"     : False,
    "data_root"   : "data/",
    "ckpt_dir"    : "data/checkpoints/",
    "log_dir"     : "data/logs/",
    "pred_dir"    : "data/predictions/",
    "num_workers" : 0,          # 0 to avoid multiprocessing in notebook
}

summary = run_training(smoke_config)

print("\n=== Smoke-test summary ===")
for k, v in summary.items():
    if k not in ("config", "history"):
        print(f"  {k:<20}: {v}")
