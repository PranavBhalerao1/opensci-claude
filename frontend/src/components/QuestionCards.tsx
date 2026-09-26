"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { NOT_SURE, type Answer, type Message, type Question } from "@/lib/api";

type QuestionsMessage = Extract<Message, { kind: "questions" }>;
type AnswersMessage = Extract<Message, { kind: "answers" }>;

interface Props {
  message: QuestionsMessage;
  /** The answers message for these questions, once answered. */
  answered?: AnswersMessage;
  busy: boolean;
  onSubmit: (answers: Answer[]) => void;
}

export default function QuestionCards({ message, answered, busy, onSubmit }: Props) {
  const { questions, round } = message.payload;
  const [draft, setDraft] = useState<Record<string, Answer>>({});

  const answers: Record<string, Answer> = answered
    ? Object.fromEntries(answered.payload.answers.map((a) => [a.question_id, a]))
    : draft;
  const locked = Boolean(answered) || busy;
  const done = questions.filter((q) => isAnswered(answers[q.id])).length;

  const toggle = (q: Question, label: string) => {
    if (locked) return;
    setDraft((d) => {
      const cur = d[q.id] ?? { question_id: q.id, selected: [], other: null };
      let selected: string[];
      if (label === NOT_SURE || !q.multi) {
        selected = cur.selected.includes(label) ? [] : [label];
      } else {
        const base = cur.selected.filter((s) => s !== NOT_SURE);
        selected = base.includes(label) ? base.filter((s) => s !== label) : [...base, label];
      }
      return { ...d, [q.id]: { ...cur, selected } };
    });
  };

  const setOther = (q: Question, text: string) =>
    setDraft((d) => {
      const cur = d[q.id] ?? { question_id: q.id, selected: [], other: null };
      return { ...d, [q.id]: { ...cur, other: text || null } };
    });

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
        OpenScientist · Clarifying questions · Round {round}
      </div>
      <div className="prose-os mb-5">
        <ReactMarkdown>{message.payload.message}</ReactMarkdown>
      </div>

      <div className="border border-ink">
        {questions.map((q, i) => (
          <QuestionBlock
            key={q.id}
            index={i}
            total={questions.length}
            question={q}
            answer={answers[q.id]}
            locked={locked}
            auto={answered?.payload.auto ?? false}
            onToggle={(label) => toggle(q, label)}
            onOther={(text) => setOther(q, text)}
          />
        ))}

        <div className="flex items-center justify-between bg-wash px-5 py-3">
          {answered ? (
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
              {answered.payload.auto ? "Answered automatically" : "Answered"}
            </span>
          ) : (
            <>
              <span className="font-mono text-[11px] text-muted">
                {done} of {questions.length} answered
              </span>
              <button
                disabled={done < questions.length || busy}
                onClick={() => onSubmit(questions.map((q) => answers[q.id]))}
                className="bg-ink px-4 py-2 text-[13px] text-paper transition-opacity disabled:opacity-25"
              >
                Continue →
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function isAnswered(a?: Answer) {
  return Boolean(a && (a.selected.length || a.other?.trim()));
}

function QuestionBlock({
  index,
  total,
  question: q,
  answer,
  locked,
  auto,
  onToggle,
  onOther,
}: {
  index: number;
  total: number;
  question: Question;
  answer?: Answer;
  locked: boolean;
  auto: boolean;
  onToggle: (label: string) => void;
  onOther: (text: string) => void;
}) {
  const selected = new Set(answer?.selected ?? []);
  const options = [...q.options, { label: NOT_SURE, detail: "OpenScientist picks a sensible default and notes it." }];

  return (
    <div className="border-b border-rule px-5 py-5">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[11px] text-faint">
          {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </span>
        {q.multi && <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">Select any</span>}
      </div>
      <h3 className="mt-1.5 font-serif text-[19px] leading-snug">{q.question}</h3>
      <p className="mt-1 text-[13px] leading-relaxed text-muted">{q.why}</p>

      <div className="mt-4 grid gap-1.5" role={q.multi ? "group" : "radiogroup"}>
        {options.map((o) => {
          const on = selected.has(o.label);
          const dim = locked && !on;
          const notSure = o.label === NOT_SURE;
          return (
            <button
              key={o.label}
              role={q.multi && !notSure ? "checkbox" : "radio"}
              aria-checked={on}
              disabled={locked}
              onClick={() => onToggle(o.label)}
              className={`flex items-start gap-3 border px-3 py-2.5 text-left transition-colors ${
                on ? "border-ink bg-wash" : "border-rule"
              } ${locked ? "cursor-default" : "hover:border-ink"} ${dim ? "opacity-40" : ""} ${
                notSure && !on ? "border-dashed" : ""
              }`}
            >
              <Indicator on={on} round={!q.multi || notSure} />
              <span className="min-w-0">
                <span className={`block text-[14px] ${notSure ? "italic text-muted" : ""}`}>{o.label}</span>
                {!notSure && <span className="block text-[12.5px] leading-snug text-muted">{o.detail}</span>}
              </span>
            </button>
          );
        })}
      </div>

      {locked ? (
        answer?.other && (
          <p className="mt-2 border-l-2 border-ink pl-3 text-[13px] text-ink">{answer.other}</p>
        )
      ) : (
        <input
          value={answer?.other ?? ""}
          onChange={(e) => onOther(e.target.value)}
          placeholder="Something else? Add detail here…"
          className="mt-2 w-full border-b border-rule bg-transparent py-1.5 text-[13px] outline-none placeholder:text-faint focus:border-ink"
        />
      )}

      {auto && answer?.rationale && (
        <p className="mt-3 font-mono text-[11px] leading-relaxed text-muted">
          <span className="uppercase tracking-[0.12em] text-faint">Auto · </span>
          {answer.rationale}
        </p>
      )}
    </div>
  );
}

function Indicator({ on, round }: { on: boolean; round: boolean }) {
  return (
    <span
      aria-hidden
      className={`mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center border border-ink ${
        round ? "rounded-full" : ""
      }`}
    >
      {on && <span className={`h-2 w-2 bg-ink ${round ? "rounded-full" : ""}`} />}
    </span>
  );
}
