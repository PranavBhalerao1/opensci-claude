"use client";

import { useState } from "react";

import { useAuth } from "@/lib/supabase/AuthProvider";
import Film from "./Film";

const CHAPTERS = [
  { n: 1, title: "Ask a question", note: "The researcher types a question in plain words and answers a few clarifying questions." },
  { n: 2, title: "Literature review", note: "Agents search, screen and read the literature, and map what is already known." },
  { n: 3, title: "Research gaps", note: "It proposes open gaps and checks each one for novelty against what it read." },
  { n: 4, title: "Research plan", note: "A phased plan with tasks, audited by an expert reviewer before anything runs." },
  { n: 5, title: "Blueprint", note: "Agents and tasks are laid out, and it writes the tools and data connectors it needs." },
  { n: 6, title: "Execution", note: "Tasks run on OpenScientist Cloud; failures are retried with fixes and it learns reusable skills." },
  { n: 7, title: "The paper", note: "Results are written up as a paper with figures, tables and citations to what it read." },
  { n: 8, title: "Scientific review", note: "A fresh reviewer panel scores the paper; it repairs the issues and re-runs what changed." },
];

const MESSAGE =
  "We're currently onboarding scientists, researchers and labs and giving them free trials, so we're very low on funds right now. Please bear with us! For now, here's a demo of a full OpenScientist research run.";

/** The only screen a walkthrough account sees: notes first, then the scripted run with a notes panel. */
export default function Walkthrough({ email }: { email: string }) {
  const { signOut } = useAuth();
  const [started, setStarted] = useState(false);
  const [run, setRun] = useState({ key: 0, from: 0 });
  const [chapter, setChapter] = useState(0);
  const [slow, setSlow] = useState(false);
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);

  const play = (from: number) => {
    setRun((r) => ({ key: r.key + 1, from }));
    setChapter(from);
    setDone(false);
  };

  if (!started) {
    return (
      <div className="fixed inset-0 overflow-y-auto bg-paper">
        <div className="mx-auto max-w-2xl px-4 py-14 sm:px-6 sm:py-20">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">OpenScientist</p>
          <h1 className="mt-4 font-serif text-[64px] leading-[1] text-ink sm:text-[96px]">
            Hey <span className="italic">YC</span> 👋
          </h1>
          <p className="mt-8 font-serif text-[24px] leading-snug text-ink sm:text-[30px]">{MESSAGE}</p>

          <div className="mt-10 flex flex-wrap items-center gap-4">
            <button
              onClick={() => {
                setStarted(true);
                play(0);
              }}
              className="bg-ink px-6 py-3 text-[14px] text-paper hover:opacity-90"
            >
              Start the demo →
            </button>
            <span className="text-[13px] text-faint">Best viewed full screen on a laptop or desktop.</span>
          </div>

          <p className="mt-16 flex items-center justify-between border-t border-rule pt-4 font-mono text-[11px] text-faint">
            <span className="truncate">{email}</span>
            <button onClick={() => void signOut()} className="uppercase tracking-wider hover:text-ink">
              Sign out
            </button>
          </p>
        </div>
      </div>
    );
  }

  const panelOpen = open || done;

  return (
    <>
      <Film
        key={`${run.key}-${slow ? 1 : 1.4}`}
        from={run.from}
        speed={slow ? 1 : 1.4}
        hideCursor={false}
        onChapter={setChapter}
        onDone={() => setDone(true)}
      />

      {!panelOpen && (
        <button
          onClick={() => setOpen(true)}
          className="fixed right-0 top-1/2 z-[200] -translate-y-1/2 border border-r-0 border-ink bg-ink px-2 py-4 font-mono text-[11px] uppercase tracking-[0.2em] text-paper [writing-mode:vertical-rl] hover:opacity-90"
        >
          Notes
        </button>
      )}

      {panelOpen && (
        <aside className="film-slide fixed bottom-0 right-0 top-0 z-[200] flex w-[min(380px,100vw)] flex-col border-l border-ink bg-paper shadow-[-12px_0_40px_rgba(0,0,0,0.12)]">
          <div className="flex items-center justify-between border-b border-rule px-5 py-4">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink">
              {done ? "Demo complete" : "Notes"}
            </p>
            <button
              onClick={() => {
                setOpen(false);
                setDone(false);
              }}
              className="font-mono text-[11px] uppercase tracking-wider text-muted hover:text-ink"
            >
              Close ✕
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            <p className="font-serif text-[18px] leading-snug text-ink">Hey YC 👋</p>
            <p className="mt-2 text-[13px] leading-relaxed text-muted">{MESSAGE}</p>

            <p className="mt-7 font-mono text-[10px] uppercase tracking-wider text-faint">Stages · click to jump</p>
            <ol className="mt-2 border-t border-rule">
              {CHAPTERS.map((c) => {
                const now = chapter === c.n;
                return (
                  <li key={c.n} className="border-b border-rule">
                    <button
                      onClick={() => {
                        play(c.n);
                        setOpen(false);
                      }}
                      className={`grid w-full grid-cols-[28px_1fr] gap-2 py-3 text-left hover:bg-wash ${now ? "bg-wash" : ""}`}
                    >
                      <span className={`pl-1 font-mono text-[11px] ${now ? "text-ink" : "text-faint"}`}>
                        {String(c.n).padStart(2, "0")}
                      </span>
                      <span>
                        <span className={`block text-[13px] ${now ? "text-ink" : "text-ink/80"}`}>
                          {c.title}
                          {now && !done && <span className="ml-2 font-mono text-[10px] uppercase text-muted">● playing</span>}
                        </span>
                        <span className="mt-0.5 block text-[12px] leading-snug text-muted">{c.note}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="space-y-3 border-t border-rule px-5 py-4">
            <div className="flex gap-2">
              <button
                onClick={() => {
                  play(0);
                  setOpen(false);
                }}
                className="flex-1 bg-ink px-3 py-2 text-[13px] text-paper hover:opacity-90"
              >
                ↺ Replay from start
              </button>
              <button
                onClick={() => setSlow((s) => !s)}
                className="border border-ink px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-ink hover:bg-wash"
                title="Playback speed"
              >
                {slow ? "Speed · 1×" : "Speed · fast"}
              </button>
            </div>
            <p className="flex items-center justify-between font-mono text-[11px] text-faint">
              <button onClick={() => setStarted(false)} className="uppercase tracking-wider hover:text-ink">
                ← Intro notes
              </button>
              <button onClick={() => void signOut()} className="uppercase tracking-wider hover:text-ink">
                Sign out
              </button>
            </p>
          </div>
        </aside>
      )}
    </>
  );
}
