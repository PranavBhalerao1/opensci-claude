
import pandas as pd

# Read one file to see the exact column names pandas produces
df_test = pd.read_csv("data/metrics_seed42_noaug.csv")
print("Columns:", df_test.columns.tolist())
print("Shape:", df_test.shape)
print("Head(3):\n", df_test.head(3))
print("Dtypes:\n", df_test.dtypes)
