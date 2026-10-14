import Link from "next/link";

/** Header and footer shared by the public pages (landing, waitlist). */
export function SiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
      <Link href="/" className="font-serif text-[22px] leading-none tracking-tight">
        Open<span className="italic">Scientist</span>
      </Link>
      <nav className="flex items-center gap-7 font-mono text-[11px] uppercase tracking-[0.14em]">
        <Link href="/#method" className="text-muted transition-colors hover:text-ink max-sm:hidden">
          Method
        </Link>
        <Link href="/#principles" className="text-muted transition-colors hover:text-ink max-sm:hidden">
          Principles
        </Link>
        {/* Plain <a>: /demo is a static page outside the Next.js router. */}
        <a href="/demo" className="text-muted transition-colors hover:text-ink max-sm:hidden">
          Demo
        </a>
        <Link href="/login" className="text-muted transition-colors hover:text-ink">
          Sign in
        </Link>
        <Link href="/waitlist" className="border border-ink bg-ink px-3.5 py-1.5 text-paper transition-opacity hover:opacity-85">
          Join waitlist
        </Link>
      </nav>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mx-auto flex w-full max-w-6xl justify-between px-6 py-6 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
      <span>© {new Date().getFullYear()} OpenScientist</span>
      <span>Research, for everyone</span>
    </footer>
  );
}
