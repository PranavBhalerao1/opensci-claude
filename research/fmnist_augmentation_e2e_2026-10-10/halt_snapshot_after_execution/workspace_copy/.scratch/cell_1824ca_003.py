
# Inspect raw per-epoch CSVs to cross-validate
for fname in ['data/metrics_seed42_noaug.csv', 'data/metrics_seed42_aug.csv',
              'data/metrics_seed123_noaug.csv', 'data/metrics_seed123_aug.csv']:
    d = pd.read_csv(fname)
    print(f"\n{fname}  shape={d.shape}")
    print(d.head(3).to_string())
    print(d.tail(2).to_string())
