import type { Project } from "@/lib/api";
import { useAuth } from "@/lib/supabase/AuthProvider";

interface Props {
  projects: Project[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({ projects, activeId, onSelect, onNew, onDelete }: Props) {
  const { user, signOut } = useAuth();
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-rule bg-paper max-md:hidden">
      <div className="px-5 pt-5 pb-4">
        <div className="font-serif text-[22px] leading-none tracking-tight">
          Open<span className="italic">Scientist</span>
        </div>
        <div className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Research, for everyone</div>
      </div>
      <div className="px-3">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-between border border-ink px-3 py-2 text-[13px] transition-colors hover:bg-ink hover:text-paper"
        >
          New investigation <span className="font-mono">+</span>
        </button>
      </div>
      <div className="mt-6 px-5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Investigations</div>
      <nav className="mt-2 flex-1 overflow-y-auto px-2 pb-4">
        {projects.length === 0 && <p className="px-3 py-2 text-[13px] text-faint">None yet.</p>}
        {projects.map((p) => (
          <div
            key={p.id}
            className={`group flex items-center rounded-sm ${p.id === activeId ? "bg-wash" : "hover:bg-wash"}`}
          >
            <button onClick={() => onSelect(p.id)} className="min-w-0 flex-1 px-3 py-2 text-left">
              <div className={`truncate text-[13px] ${p.id === activeId ? "text-ink" : "text-muted"}`}>{p.title}</div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-faint">{p.stage}</div>
            </button>
            <button
              onClick={() => onDelete(p.id)}
              aria-label="Delete investigation"
              className="mr-2 hidden px-1 font-mono text-[12px] text-faint hover:text-ink group-hover:block"
            >
              ×
            </button>
          </div>
        ))}
      </nav>
      {user && (
        <div className="flex items-center justify-between gap-2 border-t border-rule px-3 py-3">
          <span className="min-w-0 truncate font-mono text-[11px] text-faint" title={user.email ?? undefined}>
            {user.email}
          </span>
          <button
            onClick={signOut}
            className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-muted hover:text-ink"
          >
            Sign out
          </button>
        </div>
      )}
    </aside>
  );
}
