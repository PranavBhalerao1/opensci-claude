
import json

with open('analysis/crossover_summary.json') as f:
    crossover = json.load(f)
print(json.dumps(crossover, indent=2))
