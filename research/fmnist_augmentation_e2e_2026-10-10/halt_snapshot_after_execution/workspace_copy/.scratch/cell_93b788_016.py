
import pandas as pd

# Summary table of epoch-5 and epoch-30 test accuracies for all 4 runs
print("=" * 60)
print("ACCURACY SUMMARY: Epoch-5 and Epoch-30 test_acc")
print("=" * 60)

results = {}
csvs = {
    'seed42_noaug': 'data/metrics_seed42_noaug.csv',
    'seed42_aug':   'data/metrics_seed42_aug.csv',
    'seed123_noaug':'data/metrics_seed123_noaug.csv',
    'seed123_aug':  'data/metrics_seed123_aug.csv',
}

print(f"\n{'Condition':<20} {'Ep-5 test_acc':>15} {'Ep-30 test_acc':>15}")
print("-" * 52)
for name, path in csvs.items():
    df = pd.read_csv(path)
    ep5_test  = df['test_acc'].iloc[4]    # epoch 5 (index 4)
    ep30_test = df['test_acc'].iloc[-1]   # epoch 30 (last)
    results[name] = {'ep5': ep5_test, 'ep30': ep30_test}
    print(f"{name:<20} {ep5_test:>14.2f}% {ep30_test:>14.2f}%")

print("\nAugmentation effect at epoch 5:")
for seed in [42, 123]:
    noaug_ep5 = results[f'seed{seed}_noaug']['ep5']
    aug_ep5   = results[f'seed{seed}_aug']['ep5']
    diff = aug_ep5 - noaug_ep5
    print(f"  seed={seed}: aug({aug_ep5:.2f}%) - noaug({noaug_ep5:.2f}%) = {diff:+.2f}%")

print("\nAugmentation effect at epoch 30:")
for seed in [42, 123]:
    noaug_ep30 = results[f'seed{seed}_noaug']['ep30']
    aug_ep30   = results[f'seed{seed}_aug']['ep30']
    diff = aug_ep30 - noaug_ep30
    print(f"  seed={seed}: aug({aug_ep30:.2f}%) - noaug({noaug_ep30:.2f}%) = {diff:+.2f}%")
