import Link from "next/link";

export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Link href="/" className="font-serif text-[22px] leading-none tracking-tight">
          Open<span className="italic">Scientist</span>
        </Link>
        <h1 className="mt-8 font-serif text-[28px] leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-2 text-[14px] leading-relaxed text-muted">{subtitle}</p>}
        <div className="mt-8">{children}</div>
        {footer && <div className="mt-6 font-mono text-[12px] text-muted">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({
  label,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{label}</span>
      <input
        {...props}
        className="mt-1.5 w-full border border-rule bg-paper px-3 py-2 text-[14px] outline-none transition-colors focus:border-ink"
      />
    </label>
  );
}

export function SubmitButton({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="flex w-full items-center justify-center bg-ink px-4 py-2.5 font-mono text-[12px] uppercase tracking-[0.1em] text-paper transition-opacity hover:opacity-90 disabled:opacity-40"
    >
      {busy ? "…" : children}
    </button>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="border border-ink px-3 py-2 font-mono text-[12px]">
      <span className="uppercase tracking-wider">Error</span> — {message}
    </div>
  );
}

export function SuccessNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="border border-rule bg-wash px-3 py-2 text-[13px] text-muted">{message}</div>;
}

export function GoogleButton({ onClick, busy }: { onClick: () => void; busy: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="flex w-full items-center justify-center gap-2 border border-ink px-4 py-2.5 text-[13px] transition-colors hover:bg-ink hover:text-paper disabled:opacity-40"
    >
      <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
        <path
          fill="currentColor"
          d="M45 24c0-1.6-.1-2.8-.4-4H24v8h11.9c-.5 3-2.3 6.5-5.9 8.9l9.1 7C44.5 39.5 45 32.5 45 24z"
        />
        <path
          fill="currentColor"
          d="M24 46c6.2 0 11.4-2 15.1-5.6l-9.1-7c-2.2 1.5-5 2.4-8.4 2.4-6.4 0-11.8-4.3-13.7-10H4.8v7C8.6 41.8 15.7 46 24 46z"
        />
        <path fill="currentColor" d="M10.3 25.8c-.5-1.5-.8-3-.8-4.6s.3-3.1.8-4.6V9.6H4.8C2.9 13 2 17.4 2 21.2s.9 8.2 2.8 11.6z" />
        <path
          fill="currentColor"
          d="M24 9.6c3.7 0 6.4 1.6 8.1 3.2l7.1-6.9C34.9 2.3 30 0 24 0 15.7 0 8.6 4.2 4.8 9.6l5.5 7c1.9-5.7 7.3-10 13.7-10z"
        />
      </svg>
      Continue with Google
    </button>
  );
}
