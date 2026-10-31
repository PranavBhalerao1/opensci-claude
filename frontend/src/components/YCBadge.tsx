/** "Backed by Y Combinator" in the site's bordered mono badge, with YC's orange mark. */
export function YCBadge() {
  return (
    <div className="flex items-center gap-2.5 border border-ink bg-paper px-4 py-1.5 font-mono text-[12.5px] uppercase tracking-[0.18em]">
      <span>Backed by</span>
      <span
        aria-hidden
        className="flex h-[20px] w-[20px] items-center justify-center bg-[#F26625] font-sans text-[13px] font-bold leading-none tracking-normal text-white"
      >
        Y
      </span>
      <span>Combinator</span>
    </div>
  );
}
