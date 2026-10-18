"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { meApi, type Me } from "@/lib/api";
import { pollWhileVisible } from "@/lib/poll";
import { useAuth } from "@/lib/supabase/AuthProvider";
import AuthShell, { ErrorNote } from "./auth/AuthShell";

const BetaContext = createContext<Me | null>(null);
const RefreshContext = createContext<() => void>(() => {});

/** The signed-in user's verified beta status (always approved inside the gate). */
export function useBeta(): Me | null {
  return useContext(BetaContext);
}

/** Re-read the beta status now (e.g. when work that spends credits starts or stops). */
export function useBetaRefresh(): () => void {
  return useContext(RefreshContext);
}

/**
 * Private-beta gate. Fails closed: the app renders only once /api/me has confirmed
 * the account is approved. Polls so approval (and the usage line) update live: every 30 s
 * while awaiting approval, every 5 minutes once approved, never while the tab is hidden,
 * and once whenever the tab comes back into view.
 */
const PENDING_POLL_MS = 30_000;
const APPROVED_POLL_MS = 300_000;

export default function BetaGate({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      meApi
        .get()
        .then((m) => {
          setMe(m);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const approved = Boolean(me?.beta_approved);
  useEffect(() => pollWhileVisible(load, approved ? APPROVED_POLL_MS : PENDING_POLL_MS), [load, approved]);

  // A failed recheck takes precedence over the last saved status, so a stale
  // pending or approved screen is never shown when access can't be verified.
  if (me?.beta_approved && !failed)
    return (
      <RefreshContext.Provider value={load}>
        <BetaContext.Provider value={me}>{children}</BetaContext.Provider>
      </RefreshContext.Provider>
    );

  const footer = (
    <span className="flex items-center justify-between gap-2">
      <span className="min-w-0 truncate">{user?.email}</span>
      <button onClick={signOut} className="shrink-0 uppercase tracking-wider hover:text-ink">
        Sign out
      </button>
    </span>
  );

  if (me && !failed) {
    return (
      <AuthShell title="Awaiting beta approval" footer={footer}>
        <div className="space-y-3 text-[14px] leading-relaxed text-muted">
          <p>OpenScientist is currently in private beta.</p>
          <p>Your account has been created successfully and is awaiting beta approval.</p>
          <p>We&apos;ll enable your account once your request is approved.</p>
          <p className="border-t border-rule pt-3">
            Don&apos;t want to wait?{" "}
            <a href="/pricing" className="text-ink underline underline-offset-2">
              Choose a plan
            </a>{" "}
            and start right away.
          </p>
        </div>
      </AuthShell>
    );
  }

  if (failed) {
    return (
      <AuthShell title="Checking access" footer={footer}>
        <ErrorNote message="We couldn't verify your beta access right now. Please try again in a moment." />
        <button
          onClick={() => void load()}
          className="mt-4 border border-ink px-4 py-2 text-[13px] transition-colors hover:bg-ink hover:text-paper"
        >
          Try again
        </button>
      </AuthShell>
    );
  }

  return (
    <div className="flex h-full items-center justify-center font-mono text-[12px] text-faint">Checking access…</div>
  );
}
