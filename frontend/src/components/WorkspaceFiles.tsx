"use client";

import { useEffect, useState } from "react";

import { executionApi } from "@/lib/api";
import { useAuth } from "@/lib/supabase/AuthProvider";

const IMAGE = /\.(png|jpe?g|gif|svg|webp)$/i;
const TEXT = /\.(csv|tsv|json|md|txt|py|ya?ml|tex|bib|r|qmd|log)$/i;
const PREVIEW_LINES = 200;

export default function WorkspaceFiles({
  projectId,
  focus,
  onClose,
}: {
  projectId: string;
  focus?: string;
  onClose: () => void;
}) {
  const [files, setFiles] = useState<{ path: string; size: number }[] | null>(null);
  const [selected, setSelected] = useState<string | null>(focus ?? null);

  useEffect(() => {
    executionApi.files(projectId).then(setFiles).catch(() => setFiles([]));
  }, [projectId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const groups = new Map<string, { path: string; size: number }[]>();
  for (const f of files ?? []) {
    const top = f.path.includes("/") ? f.path.split("/")[0] : "·";
    groups.set(top, [...(groups.get(top) ?? []), f]);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button aria-label="Close files" onClick={onClose} className="absolute inset-0 bg-ink/20" />
      <div className="relative flex h-full w-full max-w-[1040px] flex-col border-l border-ink bg-paper">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-ink px-6">
          <div className="flex items-baseline gap-4">
            <span className="font-serif text-[20px]">Workspace</span>
            <span className="font-mono text-[11px] text-faint">{files?.length ?? "…"} files</span>
          </div>
          <button onClick={onClose} className="font-mono text-[18px] leading-none text-muted hover:text-ink" aria-label="Close">
            ×
          </button>
        </header>
        <div className="flex min-h-0 flex-1">
          <nav className="w-72 shrink-0 overflow-y-auto border-r border-rule py-2">
            {files?.length === 0 && <p className="px-5 py-3 text-[13px] text-faint">No files yet.</p>}
            {[...groups.entries()].map(([dir, items]) => (
              <div key={dir} className="mb-2">
                <div className="px-5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{dir}/</div>
                {items.map((f) => (
                  <button
                    key={f.path}
                    onClick={() => setSelected(f.path)}
                    className={`flex w-full justify-between gap-2 px-5 py-1 text-left font-mono text-[11.5px] ${
                      selected === f.path ? "bg-ink text-paper" : "hover:bg-wash"
                    }`}
                  >
                    <span className="truncate">{dir === "·" ? f.path : f.path.slice(dir.length + 1)}</span>
                    <span className={selected === f.path ? "text-faint" : "text-faint"}>{fmt(f.size)}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>
          <div className="min-w-0 flex-1 overflow-auto">
            {selected ? <Preview projectId={projectId} path={selected} /> : (
              <p className="p-6 text-[13px] text-faint">Select a file to preview it.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Preview({ projectId, path }: { projectId: string; path: string }) {
  const { session } = useAuth();
  const url = executionApi.fileUrl(projectId, path, session?.access_token ?? null);
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (TEXT.test(path)) {
      fetch(url)
        .then((r) => r.text())
        .then((t) => !cancelled && setText(t))
        .catch(() => !cancelled && setText("Could not load file."));
    }
    return () => {
      cancelled = true;
      setText(null);
    };
  }, [url, path]);

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="truncate font-mono text-[12.5px]">{path}</span>
        <a href={url} download className="shrink-0 border border-ink px-3 py-1 font-mono text-[11px] hover:bg-ink hover:text-paper">
          ↓ Download
        </a>
      </div>
      {IMAGE.test(path) ? (
        // eslint-disable-next-line @next/next/no-img-element -- workspace files are served by the API, not optimised assets
        <img src={url} alt={path} className="max-w-full border border-rule" />
      ) : TEXT.test(path) ? (
        text === null ? (
          <p className="font-mono text-[12px] text-muted">Loading…</p>
        ) : /\.(csv|tsv)$/i.test(path) ? (
          <Table text={text} sep={path.endsWith(".tsv") ? "\t" : ","} />
        ) : (
          <pre className="whitespace-pre-wrap break-words border border-rule bg-wash p-4 font-mono text-[12px] leading-relaxed">
            {text.split("\n").slice(0, PREVIEW_LINES).join("\n")}
            {text.split("\n").length > PREVIEW_LINES ? "\n… (download for the full file)" : ""}
          </pre>
        )
      ) : (
        <p className="text-[13px] text-muted">No preview for this file type. Download it to open.</p>
      )}
    </div>
  );
}

function Table({ text, sep }: { text: string; sep: string }) {
  // Simple split: fine for previews of machine-written CSVs; quoted separators may misalign.
  const rows = text.trim().split("\n");
  const head = rows[0]?.split(sep) ?? [];
  const body = rows.slice(1, 101).map((r) => r.split(sep));
  return (
    <div className="overflow-x-auto">
      <p className="mb-2 font-mono text-[11px] text-muted">
        {rows.length - 1} rows × {head.length} columns{rows.length > 101 ? " · first 100 shown" : ""}
      </p>
      <table className="border-collapse font-mono text-[11.5px]">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} className="border-b border-ink px-3 py-1 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className="border-b border-rule px-3 py-1">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmt(n: number) {
  return n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
}
