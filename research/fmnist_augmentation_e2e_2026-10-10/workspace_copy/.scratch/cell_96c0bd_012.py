
# Detailed data check — spot-verify epoch-5 values for each panel
import pandas as pd

df = pd.read_csv('analysis/combined_metrics.csv')

print("=== Epoch-5 Spot Check for All Four Panels ===")
for seed in [42, 123]:
    for aug in [False, True]:
        sub = df[(df['seed']==seed) & (df['augmented']==aug)]
        ep5 = sub[sub['epoch']==5].iloc[0]
        ep30 = sub[sub['epoch']==30].iloc[0]
        label = f"Seed {seed} | {'Aug' if aug else 'No-Aug'}"
        print(f"\n{label}")
        print(f"  Ep 5  → train_loss={ep5.train_loss:.4f}, val_acc={ep5.val_acc:.2f}%")
        print(f"  Ep 30 → train_loss={ep30.train_loss:.4f}, val_acc={ep30.val_acc:.2f}%")
        print(f"  Loss Δ ep5→ep30: {ep30.train_loss - ep5.train_loss:+.4f}")
        print(f"  Acc  Δ ep5→ep30: {ep30.val_acc - ep5.val_acc:+.2f} pp")
