
pathlib.Path('figures').mkdir(exist_ok=True)

# ── colour / style palette consistent with the study ─────────────────────────
C_SEED42  = '#1f77b4'   # blue
C_SEED123 = '#ff7f0e'   # orange
C_MEAN    = 'black'
C_ZERO    = '#888888'
C_EP5     = C_ZERO      # epoch-5 vertical shading

epochs      = df['epoch'].values
gap42       = df['gap_seed42'].values
gap123      = df['gap_seed123'].values
mean_gap    = df['mean_gap'].values

# Epoch-5 values
ep5_42  = float(df.loc[df['epoch'] == 5, 'gap_seed42'])
ep5_123 = float(df.loc[df['epoch'] == 5, 'gap_seed123'])
ep5_mean= float(df.loc[df['epoch'] == 5, 'mean_gap'])

# ── Figure setup ──────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

# ── Zero reference line ───────────────────────────────────────────────────────
ax.axhline(0, color=C_ZERO, linewidth=1.4, linestyle='--',
           zorder=1, label='Zero reference (gap = 0)')

# ── Per-seed gap lines ────────────────────────────────────────────────────────
ax.plot(epochs, gap42,
        color=C_SEED42, linewidth=1.5, linestyle='-',
        zorder=3, label='Gap seed 42 (aug − no-aug)')

ax.plot(epochs, gap123,
        color=C_SEED123, linewidth=1.5, linestyle='--',
        zorder=3, label='Gap seed 123 (aug − no-aug)')

# ── Bold mean line ────────────────────────────────────────────────────────────
ax.plot(epochs, mean_gap,
        color=C_MEAN, linewidth=3.0, linestyle='-',
        zorder=4, label='Mean gap (bold)')

# ── Epoch-5 vertical marker ───────────────────────────────────────────────────
ax.axvline(5, color=C_EP5, linewidth=1.0, linestyle=':', alpha=0.7, zorder=2)
ax.text(5.35, ax.get_ylim()[0] if False else -5.5,
        'Epoch 5', rotation=90, va='bottom', ha='left',
        fontsize=8, color=C_EP5, style='italic')

# ── Epoch-5 filled circle markers ─────────────────────────────────────────────
ax.scatter([5], [ep5_42],  color=C_SEED42,  s=70, zorder=6,
           label=f'Seed 42 @ ep5: {ep5_42:+.2f} pp')
ax.scatter([5], [ep5_123], color=C_SEED123, s=70, marker='D', zorder=6,
           label=f'Seed 123 @ ep5: {ep5_123:+.2f} pp')
ax.scatter([5], [ep5_mean], color=C_MEAN, s=90, zorder=7,
           marker='*', label=f'Mean @ ep5: {ep5_mean:+.2f} pp')

# small offset labels for the epoch-5 points
ax.annotate(f'{ep5_42:+.2f} pp',  xy=(5, ep5_42),
            xytext=(6.0, ep5_42 + 0.25),
            fontsize=8, color=C_SEED42,
            arrowprops=dict(arrowstyle='->', color=C_SEED42, lw=0.8))
ax.annotate(f'{ep5_123:+.2f} pp', xy=(5, ep5_123),
            xytext=(6.0, ep5_123 - 0.55),
            fontsize=8, color=C_SEED123,
            arrowprops=dict(arrowstyle='->', color=C_SEED123, lw=0.8))

# ── Crossover annotation ──────────────────────────────────────────────────────
if crossover_epoch is not None:
    ax.axvline(crossover_epoch, color='crimson', linewidth=1.6,
               linestyle='-.', zorder=5)
    ax.text(crossover_epoch + 0.4, -0.6,
            f'Crossover (epoch {crossover_epoch})',
            color='crimson', fontsize=9, va='center', rotation=90)
else:
    # Closest-approach annotation at epoch 29
    closest_ep  = int(df.loc[df['mean_gap'].idxmax(), 'epoch'])
    closest_val = float(df['mean_gap'].max())
    ax.annotate(
        f'No crossover within 30 epochs\n'
        f'(closest: ep {closest_ep}, mean gap = {closest_val:+.3f} pp)',
        xy=(closest_ep, closest_val),
        xytext=(20, 0.8),
        fontsize=8.5, color='dimgrey',
        bbox=dict(boxstyle='round,pad=0.4', fc='lightyellow',
                  ec='darkgoldenrod', alpha=0.85),
        arrowprops=dict(arrowstyle='->', color='dimgrey', lw=0.9),
        zorder=8
    )

# ── Regime classification banner ─────────────────────────────────────────────
regime_txt = ('Regime: underfitting-penalty-confirmed\n'
              'Both seeds: gap < 0 at epoch 5 (mean = −2.70 pp)')
ax.text(0.02, 0.97, regime_txt,
        transform=ax.transAxes, fontsize=7.5,
        va='top', ha='left', style='italic',
        bbox=dict(boxstyle='round,pad=0.35', fc='#eef4fb',
                  ec='#1f77b4', alpha=0.9))

# ── Light shading for underfitting zone (epochs 1-5) ─────────────────────────
ax.axvspan(1, 5, alpha=0.06, color='steelblue', zorder=0,
           label='Underfitting zone (ep 1–5)')

# ── Axes labels, title, limits ────────────────────────────────────────────────
ax.set_xlabel('Training Epoch', fontsize=12, labelpad=6)
ax.set_ylabel('Accuracy Gap: Aug − No-Aug (pp)', fontsize=12, labelpad=6)
ax.set_title('Augmentation Benefit Trajectory\n'
             'Fashion-MNIST · Small CNN · 2 seeds × 30 epochs',
             fontsize=13, fontweight='bold', pad=10)

ax.set_xlim(1, 30)
ax.set_ylim(-6.5, 1.8)
ax.set_xticks(range(1, 31, 1))
ax.tick_params(axis='x', labelsize=7, rotation=0)
ax.tick_params(axis='y', labelsize=9)
ax.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
ax.grid(axis='y', alpha=0.3, linewidth=0.6)
ax.grid(axis='x', alpha=0.15, linewidth=0.5)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_handles = [
    Line2D([0],[0], color=C_ZERO,    lw=1.4, ls='--',  label='Zero reference (gap = 0)'),
    Line2D([0],[0], color=C_SEED42,  lw=1.5, ls='-',   label='Seed 42'),
    Line2D([0],[0], color=C_SEED123, lw=1.5, ls='--',  label='Seed 123'),
    Line2D([0],[0], color=C_MEAN,    lw=3.0, ls='-',   label='Mean gap'),
    plt.scatter([],[],  color=C_SEED42,  s=60,          label=f'Seed 42 @ ep5: {ep5_42:+.2f} pp'),
    plt.scatter([],[],  color=C_SEED123, s=60, marker='D', label=f'Seed 123 @ ep5: {ep5_123:+.2f} pp'),
    plt.scatter([],[],  color=C_MEAN,    s=80, marker='*',  label=f'Mean @ ep5: {ep5_mean:+.2f} pp'),
    mpatches.Patch(fc='steelblue', alpha=0.15, label='Underfitting zone (ep 1–5)'),
]
ax.legend(handles=legend_handles, loc='lower right',
          fontsize=8, framealpha=0.88, ncol=2,
          edgecolor='#cccccc')

plt.tight_layout(pad=0.8)

# ── Save PNG ──────────────────────────────────────────────────────────────────
png_path = 'figures/fig2_accuracy_gap.png'
pdf_path = 'figures/fig2_accuracy_gap.pdf'
fig.savefig(png_path, dpi=300, bbox_inches='tight')
fig.savefig(pdf_path, dpi=300, bbox_inches='tight', format='pdf')
plt.close(fig)

# ── Verify outputs ────────────────────────────────────────────────────────────
for p in [png_path, pdf_path]:
    sz = pathlib.Path(p).stat().st_size
    print(f"{p}  →  {sz/1024:.1f} KB  {'✓ OK' if sz > 20_000 else '✗ TOO SMALL'}")
