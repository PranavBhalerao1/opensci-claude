
import os

# List figures
figs = [f for f in os.listdir('figures') if not f.startswith('_')]
print("Figures:", sorted(figs))

# Check context files
import json
with open('context/plan.json') as f:
    plan = json.load(f)
print("\nPlan keys:", list(plan.keys()))
