/** "Backed by Y Combinator" in the site's bordered mono badge, with YC's orange mark. */
export function YCBadge() {
  return (
    <div className="flex items-center gap-2 border border-ink bg-paper px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em]">
      <span>Backed by</span>
      <span
        aria-hidden
        className="flex h-[15px] w-[15px] items-center justify-center bg-[#F26625] font-sans text-[10px] font-bold leading-none tracking-normal text-white"
      >
        Y
      </span>
      <span>Combinator</span>
    </div>
  );
}
