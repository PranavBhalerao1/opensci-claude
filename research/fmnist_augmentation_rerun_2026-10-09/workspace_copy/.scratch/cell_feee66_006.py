
# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY.md
# ═══════════════════════════════════════════════════════════════════════════

# Parse Spearman + concordance from diagnostics
import re

spearman_rho  = float(re.search(r"Spearman rho \(rho\)\s*=\s*([\-\d\.]+)", diag_txt).group(1))
spearman_p    = float(re.search(r"Two-tailed p-value\s*=\s*([\d\.]+)", diag_txt).group(1))
conc_frac     = float(re.search(r"Concordance fraction\s*:\s*([\d\.]+)", diag_txt).group(1))
conc_count    = re.search(r"Concordant sizes\s*:\s*([\d]+ / [\d]+)", diag_txt).group(1)

# GPU info
gpu_seed42  = re.search(r"Seed 42\s+.*Device:\s*(.+)", gpu_txt).group(1).strip()
gpu_seed123 = re.search(r"Seed 123\s+.*Device:\s*(.+)", gpu_txt).group(1).strip()
torch_ver   = re.search(r"torch version:\s*(.+)", gpu_txt).group(1).strip()

# Regression
a     = reg["a"]
b     = reg["b"]
r2    = reg["r2"]
pval  = reg["slope_p_value"]
Nstar = reg["N_star"]
Nstar_lo = reg["N_star_ci_low"]
Nstar_hi = reg["N_star_ci_high"]
Nstar_note = reg["N_star_note"]

# Baseline accuracy at N=60000
r60_42  = acc[(acc["size"]==60000)&(acc["seed"]==42)].iloc[0]
r60_123 = acc[(acc["size"]==60000)&(acc["seed"]==123)].iloc[0]

# Negative Δ flags
neg_sizes = delt[delt["delta_mean"] < 0]["size"].tolist()

print(f"a={a:.4f}, b={b:.4f}, R²={r2:.4f}, p={pval:.4f}")
print(f"N*={Nstar:.0f}, CI=[{Nstar_lo:.0f}, {Nstar_hi:.0f}]")
print(f"Spearman ρ={spearman_rho:.4f}, p={spearman_p:.4f}")
print(f"Concordance: {conc_count}, fraction={conc_frac:.4f}")
print(f"GPU s42={gpu_seed42}, s123={gpu_seed123}, torch={torch_ver}")
print(f"Neg Δ sizes: {neg_sizes}")
