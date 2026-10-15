import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getAdminEmail, listMembers, listPending, listWaitlist } from "@/lib/admin";
import { approveAction, inviteAction, revokeAction, setCapAction } from "./actions";
import SubmitButton from "./SubmitButton";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const usd = (n: number) => `$${n.toFixed(2)}`;

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="flex items-baseline justify-between border-b border-ink pb-2">
        <span className="font-serif text-[24px] leading-none">{title}</span>
        {count !== undefined && <span className="font-mono text-[11px] text-faint">{count}</span>}
      </h2>
      {children}
    </section>
  );
}

function CapInput({ placeholder = "Cap $" }: { placeholder?: string }) {
  return (
    <input
      name="cap"
      inputMode="decimal"
      placeholder={placeholder}
      aria-label="Spending cap in dollars"
      className="w-24 min-w-0 border border-rule bg-paper px-3 py-2.5 font-mono text-[13px] outline-none focus:border-ink"
    />
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-4 text-[14px] text-faint">{children}</p>;
}

export default async function AdminPage({ searchParams }: PageProps<"/admin">) {
  await connection(); // always per request: who is admin depends on the visitor's session
  const admin = await getAdminEmail();
  if (!admin) notFound();

  const { ok, err } = await searchParams;
  const [pending, members, waitlist] = await Promise.all([
    listPending().catch(() => null),
    listMembers().catch(() => null),
    listWaitlist().catch(() => null),
  ]);
  const memberEmails = new Set(members?.map((m) => m.email.toLowerCase()));
  const pendingEmails = new Set(pending?.map((p) => p.email.toLowerCase()));

  return (
    <div className="mx-auto max-w-2xl px-4 pt-6 pb-24">
      <header className="flex items-center justify-between">
        <Link href="/" className="font-serif text-[22px] leading-none tracking-tight">
          Open<span className="italic">Scientist</span>
        </Link>
        <span className="border border-ink px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em]">Admin</span>
      </header>

      {typeof ok === "string" && (
        <div className="mt-6 border border-ink bg-wash px-4 py-3 text-[14px]">✓ {ok}</div>
      )}
      {typeof err === "string" && (
        <div className="mt-6 border border-ink bg-ink px-4 py-3 text-[14px] text-paper">✗ {err}</div>
      )}
      {(!pending || !members) && (
        <div className="mt-6 border border-ink px-4 py-3 text-[14px]">
          Couldn&apos;t load from Supabase. Check SUPABASE_SECRET_KEY on Vercel and that the beta SQL has been run.
        </div>
      )}

      <Section title="Invite">
        <form action={inviteAction} className="mt-4 flex gap-2">
          <input
            name="email"
            type="email"
            required
            autoComplete="off"
            autoCapitalize="none"
            placeholder="email@lab.edu"
            className="min-w-0 flex-1 border border-ink bg-paper px-3 py-2.5 text-[15px] outline-none"
          />
          <CapInput />
          <SubmitButton>Send</SubmitButton>
        </form>
        <p className="mt-2 font-mono text-[11px] text-faint">Leave the cap empty for unlimited. They&apos;re approved immediately.</p>
      </Section>

      <Section title="Pending" count={pending?.length}>
        {pending && !pending.length && <Empty>No one is waiting.</Empty>}
        <ul>
          {pending?.map((p) => (
            <li key={p.email} className="border-b border-rule py-4">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate text-[15px]">{p.email}</span>
                <span className="shrink-0 font-mono text-[11px] text-faint">{ago(p.signed_up)}</span>
              </div>
              {!p.confirmed && <div className="mt-1 font-mono text-[11px] text-faint">Email not confirmed yet</div>}
              <form action={approveAction} className="mt-3 flex justify-end gap-2">
                <input type="hidden" name="email" value={p.email} />
                <CapInput />
                <SubmitButton>Approve</SubmitButton>
              </form>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Members" count={members?.length}>
        {members && !members.length && <Empty>No approved members yet.</Empty>}
        <ul>
          {members?.map((m) => (
            <li key={m.email} className="border-b border-rule py-4">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate text-[15px]">{m.email}</span>
                <span className="shrink-0 font-mono text-[12px]">
                  {usd(m.spent_usd)}
                  <span className="text-faint"> / {m.cap_usd === null ? "∞" : usd(m.cap_usd)}</span>
                </span>
              </div>
              <details className="group mt-1">
                <summary className="cursor-pointer list-none font-mono text-[11px] uppercase tracking-[0.1em] text-muted group-open:text-ink">
                  Manage
                </summary>
                <div className="mt-3 flex flex-wrap justify-end gap-2">
                  <form action={setCapAction} className="flex gap-2">
                    <input type="hidden" name="email" value={m.email} />
                    <CapInput placeholder={m.cap_usd === null ? "∞" : String(m.cap_usd)} />
                    <SubmitButton variant="outline">Set cap</SubmitButton>
                  </form>
                  <form action={revokeAction}>
                    <input type="hidden" name="email" value={m.email} />
                    <SubmitButton variant="outline" confirm={`Revoke access for ${m.email}?`}>
                      Revoke
                    </SubmitButton>
                  </form>
                </div>
                <p className="mt-2 text-right font-mono text-[11px] text-faint">Empty cap = unlimited</p>
              </details>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Waitlist" count={waitlist?.length}>
        {waitlist && !waitlist.length && <Empty>No one on the waitlist yet.</Empty>}
        {!waitlist && <Empty>Waitlist unavailable.</Empty>}
        <ul>
          {waitlist?.map((w) => {
            const status = memberEmails.has(w.email) ? "Member" : pendingEmails.has(w.email) ? "Pending" : null;
            return (
              <li key={w.email} className="flex items-center justify-between gap-3 border-b border-rule py-3">
                <div className="min-w-0">
                  <div className="truncate text-[15px]">{w.email}</div>
                  <div className="font-mono text-[11px] text-faint">{ago(w.created_at)}</div>
                </div>
                {status ? (
                  <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.1em] text-faint">{status}</span>
                ) : (
                  <form action={inviteAction} className="flex shrink-0 gap-2">
                    <input type="hidden" name="email" value={w.email} />
                    <CapInput />
                    <SubmitButton variant="outline">Invite</SubmitButton>
                  </form>
                )}
              </li>
            );
          })}
        </ul>
      </Section>

      <p className="mt-12 font-mono text-[11px] text-faint">Signed in as {admin}</p>
    </div>
  );
}
