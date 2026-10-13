
# ── color / style constants ──────────────────────────────────────────────────
COLOR_S42   = '#1f77b4'   # blue  – seed 42  (solid)
COLOR_S123  = '#ff7f0e'   # orange – seed 123 (dashed)
COLOR_MEAN  = 'black'
COLOR_ZERO  = '#888888'

# ── figure ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5.5))

# ── ZERO REFERENCE LINE  (the acceptance-critical element) ──────────────────
zline = ax.axhline(y=0, color=COLOR_ZERO, linestyle='--', linewidth=1.4,
                   label='Zero reference (gap = 0)', zorder=1)
print(f"Zero-reference line drawn at y=0: {zline}")

# ── per-seed gap lines ───────────────────────────────────────────────────────
ax.plot(epochs, gap_s42, color=COLOR_S42, linestyle='-', linewidth=1.5,
        alpha=0.85, label='Gap seed 42 (solid, blue)')
ax.plot(epochs, gap_s123, color=COLOR_S123, linestyle='--', linewidth=1.5,
        alpha=0.85, label='Gap seed 123 (dashed, orange)')

# ── bold mean line ───────────────────────────────────────────────────────────
ax.plot(epochs, mean_gap, color=COLOR_MEAN, linestyle='-', linewidth=2.8,
        label='Mean gap (bold)', zorder=3)

# ── epoch-5 markers ──────────────────────────────────────────────────────────
ax.axvline(x=5, color='dimgray', linestyle=':', linewidth=1.2,
           alpha=0.6, zorder=2)
ax.plot(5, ep5_s42,  color=COLOR_S42,  marker='o', markersize=9,
        zorder=5, linestyle='None',
        label=f'Epoch-5 seed42 ({ep5_s42:+.2f} pp)')
ax.plot(5, ep5_s123, color=COLOR_S123, marker='o', markersize=9,
        zorder=5, linestyle='None',
        label=f'Epoch-5 seed123 ({ep5_s123:+.2f} pp)')

# label the epoch-5 vertical marker
ax.text(5.3, ax.get_ylim()[0] if ax.get_ylim()[0] < -5 else -5.5,
        'Epoch 5', fontsize=8.5, color='dimgray', va='bottom')

# ── crossover annotation ─────────────────────────────────────────────────────
if crossover_epoch is not None:
    ax.axvline(x=crossover_epoch, color='crimson', linestyle='-.',
               linewidth=1.6, zorder=4,
               label=f'Crossover (epoch {crossover_epoch})')
    ax.text(crossover_epoch + 0.4,
            mean_gap[crossover_epoch - 1] + 0.3,
            f'Crossover\n(epoch {crossover_epoch})',
            fontsize=9, color='crimson', va='bottom')
else:
    # place text in upper-right area
    ax.text(0.97, 0.97, 'No crossover within 30 epochs',
            transform=ax.transAxes, fontsize=9.5,
            color='crimson', va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff0f0',
                      edgecolor='crimson', alpha=0.85))

# ── axes labels / title / legend ─────────────────────────────────────────────
ax.set_xlabel('Training Epoch', fontsize=12)
ax.set_ylabel('Accuracy Gap: Aug − No-Aug (pp)', fontsize=12)
ax.set_title('Augmentation Benefit Trajectory\n'
             'Small CNN · Fashion-MNIST · 2 Seeds × 30 Epochs',
             fontsize=13, fontweight='bold')
ax.set_xlim(1, 30)
ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
ax.yaxis.set_major_locator(ticker.MultipleLocator(1))
ax.grid(True, which='major', alpha=0.25)
ax.grid(True, which='minor', alpha=0.10)

legend = ax.legend(loc='lower right', fontsize=8.5, framealpha=0.9)

# ── tighten layout ────────────────────────────────────────────────────────────
plt.tight_layout()

# ── save PNG ─────────────────────────────────────────────────────────────────
png_path = 'figures/fig2_accuracy_gap.png'
fig.savefig(png_path, dpi=300, bbox_inches='tight')
png_size = os.path.getsize(png_path)
print(f"PNG saved: {png_path} ({png_size:,} bytes)")

# ── save PDF ─────────────────────────────────────────────────────────────────
pdf_path = 'figures/fig2_accuracy_gap.pdf'
fig.savefig(pdf_path, dpi=300, bbox_inches='tight')
pdf_size = os.path.getsize(pdf_path)
print(f"PDF saved: {pdf_path} ({pdf_size:,} bytes)")

plt.close(fig)
print("\nDone.")
