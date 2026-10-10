
# ── 5. Save bootstrap distribution CSV ───────────────────────────────────────
import os
os.makedirs('analysis', exist_ok=True)

boot_df = pd.DataFrame({
    'iter':        np.arange(1, BOOT+1),
    'N_star_boot': N_star_boot_arr
})
boot_df.to_csv('analysis/bootstrap_N_star.csv', index=False)
print(f"Saved bootstrap_N_star.csv — shape: {boot_df.shape}")
print(boot_df.head(5))
print(f"\nN_star_boot stats:\n{boot_df['N_star_boot'].describe()}")

# Verify row count
assert len(boot_df) == 5000, f"Expected 5000 rows, got {len(boot_df)}"
print("\n✓ Row count = 5000")
