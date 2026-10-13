
# Final verification — check all output files
import pandas as pd, json

print("=== analysis/combined_metrics.csv ===")
cm = pd.read_csv("analysis/combined_metrics.csv")
print(f"Shape        : {cm.shape}")
print(f"Columns      : {cm.columns.tolist()}")
print(f"NaN count    : {cm.isna().sum().sum()}")
print(f"test_acc range : [{cm['test_acc'].min():.2f}, {cm['test_acc'].max():.2f}]")
groups = cm.groupby(["seed","augmented"]).size()
print(f"Groups (30 rows each):\n{groups.to_string()}")
print(f"Unique (seed,aug) combos : {len(groups)}")

print("\n=== analysis/accuracy_gap_trajectory.csv ===")
traj = pd.read_csv("analysis/accuracy_gap_trajectory.csv")
print(traj.to_string(index=False))

print("\n=== analysis/per_seed_accuracy_gap.csv ===")
psg = pd.read_csv("analysis/per_seed_accuracy_gap.csv")
print(f"Shape: {psg.shape}")
print(psg[psg["epoch"].isin([5,10,20,30])].to_string(index=False))

print("\n=== analysis/crossover_summary.json ===")
with open("analysis/crossover_summary.json") as f:
    cs = json.load(f)
for k, v in cs.items():
    print(f"  {k}: {v}")
