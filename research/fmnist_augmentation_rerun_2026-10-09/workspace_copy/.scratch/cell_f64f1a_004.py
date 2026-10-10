
# ============================================================
# STEP 3: Seed concordance — do delta_seed42 and delta_seed123
#          have the same sign at each size?
# ============================================================
d42  = delta_df['delta_seed42'].values
d123 = delta_df['delta_seed123'].values

concordant_flags = []
concordance_detail = []
for i, sz in enumerate(sizes):
    same_sign = (np.sign(d42[i]) == np.sign(d123[i]))
    concordant_flags.append(same_sign)
    concordance_detail.append({
        'size': sz,
        'delta_seed42': d42[i],
        'delta_seed123': d123[i],
        'concordant': same_sign
    })

n_concordant = sum(concordant_flags)
concordance_frac = n_concordant / len(sizes)

print("=== SEED CONCORDANCE ===")
for row in concordance_detail:
    flag = "✓ concordant" if row['concordant'] else "✗ discordant"
    print(f"  size={row['size']:>6}: Δ42={row['delta_seed42']:+.3f}  Δ123={row['delta_seed123']:+.3f}  → {flag}")

print(f"\nConcordant: {n_concordant} / {len(sizes)}")
print(f"Concordance fraction: {concordance_frac:.4f}  ({concordance_frac*100:.1f}%)")
