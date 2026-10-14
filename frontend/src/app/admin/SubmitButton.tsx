"use client";

import { useFormStatus } from "react-dom";

/** Form button that dims and shows "…" while its Server Action runs. */
export default function SubmitButton({
  children,
  variant = "solid",
  confirm,
}: {
  children: React.ReactNode;
  variant?: "solid" | "outline";
  confirm?: string;
}) {
  const { pending } = useFormStatus();
  const style =
    variant === "solid"
      ? "bg-ink text-paper hover:opacity-90"
      : "border border-ink text-ink hover:bg-ink hover:text-paper";
  return (
    <button
      type="submit"
      disabled={pending}
      onClick={(e) => {
        if (confirm && !window.confirm(confirm)) e.preventDefault();
      }}
      className={`shrink-0 px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.1em] transition disabled:opacity-40 ${style}`}
    >
      {pending ? "…" : children}
    </button>
  );
}
