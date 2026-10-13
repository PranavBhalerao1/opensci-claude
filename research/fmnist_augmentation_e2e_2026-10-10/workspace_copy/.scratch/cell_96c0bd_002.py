
import pandas as pd
import json

# Load and inspect combined_metrics
df = pd.read_csv('analysis/combined_metrics.csv')
print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print("\nHead:\n", df.head(8))
print("\nUnique seeds:", df['seed'].unique())
print("Unique augmented:", df['augmented'].unique())
print("Epoch range:", df['epoch'].min(), '-', df['epoch'].max())
print("\nStats:\n", df[['train_loss','val_acc','test_acc']].describe())
print("\nNaN check:", df.isnull().sum().to_dict())
