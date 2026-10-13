import os, csv

out = "results/smoke_test"

# Check CSV exists and has correct structure
csv_path = os.path.join(out, "metrics.csv")
with open(csv_path) as f:
    rows = list(csv.DictReader(f))

print("=== metrics.csv ===")
print(f"Rows: {len(rows)}  (expected 2 for 2-epoch smoke test)")
for r in rows:
    print(r)

# Check no checkpoint at ep5/10/20/30 (since only 2 epochs ran)
ckpt_files = [fn for fn in os.listdir(out) if fn.startswith("checkpoint")]
print(f"\nCheckpoints in {out}: {ckpt_files}  (expected none for 2-epoch run)")

# Verify columns
assert rows[0].keys() >= {"epoch","train_loss","train_acc","val_loss","val_acc"}, \
    "Missing CSV columns!"
print("\n✓ CSV structure correct")

# Check epoch 1 train_acc < 0.85  (underfitting regime)
assert float(rows[0]["train_acc"]) < 0.85, "Epoch-1 train_acc unexpectedly high!"
print(f"✓ Epoch-1 train_acc = {float(rows[0]['train_acc']):.4f} < 0.85  (underfitting confirmed)")
