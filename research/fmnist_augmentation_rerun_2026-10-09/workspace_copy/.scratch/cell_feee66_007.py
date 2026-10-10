
import os, json, re
import pandas as pd

acc  = pd.read_csv("analysis/test_acc_summary.csv")
delt = pd.read_csv("analysis/delta_by_size.csv")
with open("analysis/regression_results.json") as f:
    reg = json.load(f)
gpu_txt  = open("analysis/gpu_device_info.txt").read()
diag_txt = open("analysis/trend_diagnostics.txt").read()

# ── parse diagnostics ─────────────────────────────────────────────────────
spearman_rho  = float(re.search(r"Spearman rho \(rho\)\s*=\s*([\-\d\.]+)", diag_txt).group(1))
spearman_p    = float(re.search(r"Two-tailed p-value\s*=\s*([\d\.]+)", diag_txt).group(1))
conc_frac     = float(re.search(r"Concordance fraction\s*:\s*([\d\.]+)", diag_txt).group(1))
conc_count_str= re.search(r"Concordant sizes\s*:\s*([\d]+ / [\d]+)", diag_txt).group(1)
gpu_seed42    = re.search(r"Seed 42\s+.*?Device:\s*(.+)", gpu_txt).group(1).strip()
gpu_seed123   = re.search(r"Seed 123\s+.*?Device:\s*(.+)", gpu_txt).group(1).strip()
torch_ver     = re.search(r"torch version:\s*(.+)", gpu_txt).group(1).strip()

a        = reg["a"];  b = reg["b"];  r2 = reg["r2"];  pval = reg["slope_p_value"]
Nstar    = reg["N_star"];  Nlo = reg["N_star_ci_low"];  Nhi = reg["N_star_ci_high"]
Nnote    = reg["N_star_note"]

r60_42   = acc[(acc["size"]==60000)&(acc["seed"]==42)].iloc[0]
r60_123  = acc[(acc["size"]==60000)&(acc["seed"]==123)].iloc[0]
neg_sizes = delt[delt["delta_mean"] < 0]["size"].tolist()

print("Parsed all fields OK")
print(f"a={a:.4f}, b={b:.4f}, R²={r2:.4f}, p={pval:.4f}")
print(f"N*={Nstar:.0f}, CI=[{Nlo:.0f}, {Nhi:.0f}], note={Nnote}")
print(f"Spearman ρ={spearman_rho:.4f}, p={spearman_p:.4f}, concordance={conc_count_str}/{conc_frac:.4f}")
print(f"GPU: s42={gpu_seed42}, s123={gpu_seed123}, torch={torch_ver}")
print(f"Neg Δ sizes: {neg_sizes}")
