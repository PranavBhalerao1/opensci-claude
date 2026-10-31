"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

/** Email signup for company updates. Account holders already receive them. */
export default function NewsSubscribe() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "already" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    const { data, error } = await createClient().rpc("subscribe_news", { p_email: email });
    if (error) {
      setError(error.code === "22023" ? error.message : "That didn't go through. Please try again in a moment.");
      setState("error");
      return;
    }
    setState(data?.already ? "already" : "done");
  }

  return (
    <div className="border-t border-rule pt-10">
      <h2 className="font-serif text-[26px] leading-tight">Get updates by email</h2>
      {state === "done" || state === "already" ? (
        <p className="mt-4 font-serif text-[18px] leading-relaxed text-muted">
          {state === "done" ? "Thanks, you're subscribed." : "You're already subscribed."}
        </p>
      ) : (
        <form onSubmit={submit} className="mt-5 flex gap-2 max-sm:flex-col">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="min-w-0 flex-1 border border-ink bg-paper px-4 py-3 text-[15px] outline-none placeholder:text-faint"
          />
          <button
            type="submit"
            disabled={state === "busy"}
            className="bg-ink px-6 py-3 font-mono text-[12px] uppercase tracking-[0.12em] text-paper transition-opacity hover:opacity-85 disabled:opacity-50"
          >
            {state === "busy" ? "Subscribing…" : "Subscribe"}
          </button>
        </form>
      )}
      {state === "error" && <p className="mt-3 text-[14px] text-ink">{error}</p>}
      <p className="mt-4 font-mono text-[11px] leading-relaxed text-faint">
        Already have an OpenScientist account? You&apos;ll receive updates automatically.
      </p>
    </div>
  );
}
