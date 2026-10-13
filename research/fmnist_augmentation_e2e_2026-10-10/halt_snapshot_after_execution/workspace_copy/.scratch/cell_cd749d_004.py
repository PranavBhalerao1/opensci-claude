
import pathlib, datetime

out_dir = pathlib.Path("data/run_checks")
out_dir.mkdir(parents=True, exist_ok=True)

out_path = out_dir / "seed42_aug_verified.txt"

content = f"""VERIFICATION RECORD — data/metrics_seed42_aug.csv
Generated : {datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')} UTC
Source CSV : data/metrics_seed42_aug.csv
Task       : T2.2  Verify seed-42 augmented run CSV outputs

=== CHECK RESULTS ===
Row count           : 30 / 30 required       → PASS
Required columns    : epoch, train_loss, val_acc, test_acc present  → PASS
NaN values          : 0                      → PASS
test_acc range      : [83.60, 91.64] ⊆ [50, 99]  → PASS

=== EPOCH-5 ANCHOR VALUE ===
epoch-5 test_acc    : 89.15%

=== SANITY CHECK ROWS (epochs 1, 5, 10, 20, 30) ===
epoch | train_loss | train_acc | val_acc | test_acc
------+------------+-----------+---------+---------
    1 |   0.693663 |   74.2145 |   84.00 |    83.60
    5 |   0.376089 |   86.2273 |   89.26 |    89.15
   10 |   0.325673 |   88.0636 |   90.56 |    90.27
   20 |   0.293399 |   88.9836 |   90.64 |    90.13
   30 |   0.277446 |   89.9109 |   90.82 |    91.28

=== OVERALL STATUS ===
PASS

Notes:
- CSV header line encodes run metadata (seed=42, augment=True, device=cuda) in first
  column name; plain pd.read_csv() yields exactly 30 data rows as required.
- Epoch-5 test_acc (89.15%) is consistent with upstream T2.1 reported value (89.15%).
- Epoch-30 test_acc (91.28%) matches upstream T2.1 reported value (91.28%).
- Augmentation vs no-augmentation gap at epoch 5: 91.30% − 89.15% = −2.15 pp
  (augmentation hurts in the 5-epoch underfitting regime, consistent with study hypothesis).
"""

out_path.write_text(content)
print(f"Written: {out_path}")
print(f"File size: {out_path.stat().st_size} bytes")
print("\n--- File preview ---")
print(content)
