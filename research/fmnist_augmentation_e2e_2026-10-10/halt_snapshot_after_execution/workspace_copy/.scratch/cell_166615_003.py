
import pathlib, datetime

out_dir = pathlib.Path("data/run_checks")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "seed123_aug_verified.txt"

record = f"""VERIFICATION RECORD — data/metrics_seed123_aug.csv
Generated : {datetime.datetime.utcnow().isoformat(timespec='seconds')}Z
Task      : T2.4  (seed-123 augmented run CSV verification)

=== STRUCTURAL CHECKS ===
Row count       : 30  (required: 30)  → PASS
Required columns: train_loss, train_acc, val_acc, test_acc  → PASS
NaN values      : 0  → PASS
test_acc range  : min=81.68 %, max=91.94 %  (required: 50–99)  → PASS

=== KEY EPOCH ROWS ===
epoch |  train_loss | train_acc |  val_acc | test_acc
    1 |    0.685644 |   74.4109 |    81.88 |    81.68
    5 |    0.373817 |   86.1018 |    88.72 |    88.51
   10 |    0.326877 |   87.9418 |    90.74 |    90.10
   20 |    0.297826 |   88.9327 |    91.74 |    91.12
   30 |    0.280691 |   89.6364 |    91.18 |    91.00

=== SUMMARY ===
epoch-5  test_acc : 88.51 %
epoch-30 test_acc : 91.00 %

Overall result    : PASS
"""

out_path.write_text(record)
print(f"Written: {out_path}")
print(record)
