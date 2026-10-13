
import pandas as pd
import numpy as np

# Load combined metrics to get val_acc at epochs 5 and 30
cm = pd.read_csv('analysis/combined_metrics.csv')
print("combined_metrics shape:", cm.shape)
print(cm.columns.tolist())

# Get training dynamics at epochs 5 and 30
for ep in [5, 30]:
    print(f"\n--- Epoch {ep} ---")
    subset = cm[cm['epoch'] == ep]
    for _, row in subset.iterrows():
        cond = 'aug' if row['augmented'] else 'noaug'
        print(f"  seed={int(row['seed'])}, {cond}: train_loss={row['train_loss']:.4f}, val_acc={row['val_acc']:.2f}%, test_acc={row['test_acc']:.2f}%")
