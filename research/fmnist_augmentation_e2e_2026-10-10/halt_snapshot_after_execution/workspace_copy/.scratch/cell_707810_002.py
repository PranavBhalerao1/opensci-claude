
import os, json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Load crossover info
with open('analysis/crossover_summary.json') as f:
    crossover = json.load(f)
print("Crossover summary:", json.dumps(crossover, indent=2))
