"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { createClient } from "@/lib/supabase/client";

interface Status {
  code: string;
  position: number;
  total: number;
  referrals: number;
  boost: number;
  already?: boolean;
}

const STORE_KEY = "os.waitlist.code";
const noSubscribe = () => () => {};

function remember(code: string | null) {
  try {
    if (code) localStorage.setItem(STORE_KEY, code);
    else localStorage.removeItem(STORE_KEY);
  } catch {}
}

function recall(): string | null {
  try {
    return localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

export default function Waitlist() {
  const params = useSearchParams();
  const ref = params.get("ref");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  // Returning visitors see their place in line instead of the form.
  useEffect(() => {
    const code = recall();
    if (!code) return;
    createClient()
      .rpc("waitlist_status", { p_code: code })
      .then(({ data, error }) => {
        if (error || !data) remember(null);
        else setStatus(data as Status);
      });
  }, []);

  const join = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error } = await createClient().rpc("join_waitlist", { p_email: email, p_ref: ref });
      if (error) throw new Error(error.message);
      remember(data.code);
      setStatus(data as Status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  if (status) return <Referral status={status} onReset={() => (remember(null), setStatus(null))} />;

  return (
    <div className="w-full max-w-md">
      <form onSubmit={join} className="flex border border-ink bg-paper max-sm:flex-col">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="you@lab.edu"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="min-w-0 flex-1 bg-transparent px-4 py-3.5 text-[15px] outline-none placeholder:text-faint"
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-ink px-6 py-3.5 font-mono text-[12px] uppercase tracking-[0.12em] text-paper transition-opacity hover:opacity-85 disabled:opacity-50"
        >
          {busy ? "Joining…" : "Join waitlist"}
        </button>
      </form>
      <div className="mt-3 h-5 font-mono text-[11px] text-muted">
        {error ? (
          <span className="text-ink">— {error}</span>
        ) : ref ? (
          <span>Invited by a friend · you’ll both move up the line</span>
        ) : (
          <span>Early access opens in waves. No spam, ever.</span>
        )}
      </div>
    </div>
  );
}

export function Referral({ status, onReset }: { status: Status; onReset: () => void }) {
  const [copied, setCopied] = useState(false);
  // window's origin only exists in the browser; "" on the server keeps hydration consistent.
  const origin = useSyncExternalStore(noSubscribe, () => window.location.origin, () => "");
  const link = `${origin}/waitlist?ref=${status.code}`;
  const text = "I just joined the waitlist for OpenScientist: run real science from a single question.";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {}
  };
  const share = [
    ["X", `https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(link)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`],
    ["Email", `mailto:?subject=${encodeURIComponent("Join me on OpenScientist")}&body=${encodeURIComponent(`${text}\n\n${link}`)}`],
  ];
  // Five referral milestones, filled in as friends join.
  const steps = [1, 3, 5, 10, 25];

  return (
    <div className="w-full max-w-xl border border-ink bg-paper text-left">
      <div className="flex items-center justify-between border-b border-ink px-5 py-2.5 font-mono text-[10px] uppercase tracking-[0.14em]">
        <span>{status.already ? "Welcome back" : "You’re on the list"}</span>
        <button onClick={onReset} className="text-faint hover:text-ink">
          Not you?
        </button>
      </div>

      <div className="grid grid-cols-2 border-b border-ink">
        <div className="border-r border-ink px-5 py-6">
          <div className="font-serif text-[56px] leading-none tracking-tight">#{status.position.toLocaleString()}</div>
          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
            Place in line · of {status.total.toLocaleString()}
          </div>
        </div>
        <div className="px-5 py-6">
          <div className="font-serif text-[56px] leading-none tracking-tight">{status.referrals}</div>
          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Friends invited</div>
        </div>
      </div>

      <div className="px-5 py-5">
        <p className="text-[14px] leading-relaxed text-muted">
          Skip the line. Every friend who joins with your link moves you up{" "}
          <span className="text-ink">{status.boost} places</span>.
        </p>
        <div className="mt-4 flex border border-ink">
          <input
            readOnly
            value={link}
            onFocus={(e) => e.currentTarget.select()}
            className="min-w-0 flex-1 bg-wash px-3 py-2.5 font-mono text-[12.5px] outline-none"
          />
          <button
            onClick={copy}
            className="w-24 bg-ink font-mono text-[11px] uppercase tracking-[0.12em] text-paper hover:opacity-85"
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {share.map(([name, href]) => (
            <a
              key={name}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="border border-rule py-2 text-center font-mono text-[11px] uppercase tracking-[0.12em] text-muted transition-colors hover:border-ink hover:text-ink"
            >
              {name}
            </a>
          ))}
        </div>

        <div className="mt-6">
          <div className="flex justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
            <span>Referrals</span>
            <span>{status.referrals} / 25</span>
          </div>
          <div className="mt-2 grid grid-cols-5 gap-1.5">
            {steps.map((n) => (
              <div key={n}>
                <div className={`h-1.5 ${status.referrals >= n ? "bg-ink" : "bg-rule"}`} />
                <div className={`mt-1.5 font-mono text-[10px] ${status.referrals >= n ? "text-ink" : "text-faint"}`}>
                  {n}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
