
import json, os
import pandas as pd

# Check files exist and inspect structure
for f in ['analysis/delta_by_size.csv', 'analysis/regression_results.json', 'analysis/bootstrap_N_star.csv']:
    exists = os.path.exists(f)
    print(f"{f}: exists={exists}")
    if exists:
        if f.endswith('.csv'):
            df = pd.read_csv(f)
            print(f"  shape={df.shape}, cols={list(df.columns)}")
            print(df.head(3).to_string())
        elif f.endswith('.json'):
            with open(f) as fh:
                d = json.load(fh)
            print(f"  keys={list(d.keys())}")
            print(json.dumps(d, indent=2))
        print()
