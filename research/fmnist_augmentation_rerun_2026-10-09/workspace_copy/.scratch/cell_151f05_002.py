
# ── 3. Compute N* and set interpretive note ───────────────────────────────────
SIZE_MIN = sizes.min()   # 500
SIZE_MAX = sizes.max()   # 60000

if b >= 0:
    N_star = 2 ** (-a / b)
    if N_star < SIZE_MIN:
        N_star_note = 'extrapolated_below_range'
    elif N_star > SIZE_MAX:
        N_star_note = 'extrapolated_above_range'
    else:
        N_star_note = 'within_tested_range'
    # Also check R²
    if r2 < 0.5:
        N_star_note += '|R2_below_0.5'
else:
    N_star = float('nan')
    N_star_note = 'no_crossover_positive_slope'

print(f"N* = {N_star:.2f}")
print(f"N* note: {N_star_note}")
print(f"Tested range: [{SIZE_MIN}, {SIZE_MAX}]")
print(f"R² = {r2:.4f} → {'FLAG: R² < 0.5' if r2 < 0.5 else 'OK'}")
