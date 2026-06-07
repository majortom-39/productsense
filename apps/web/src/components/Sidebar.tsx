import { Plus, Trash2, LogOut, Settings as SettingsIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { Project } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface Props {
  projects: Project[];
  activeProjectId: string | null;
  onSelectProject: (id: string) => void;
  onCreateProject: () => void;
  onDeleteProject: (id: string) => void;
  loading?: boolean;
  creating?: boolean;
}

export function Sidebar({
  projects,
  activeProjectId,
  onSelectProject,
  onCreateProject,
  onDeleteProject,
  loading,
  creating,
}: Props) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const initial = (user?.email?.[0] ?? "?").toUpperCase();
  const username = (user?.email?.split("@")[0] ?? "you").toLowerCase();

  return (
    <aside className="w-[260px] flex-shrink-0 flex flex-col rounded-3xl bg-card border border-border overflow-hidden">
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <img src="/Productsense_Icon Black.svg" alt="" className="h-6 w-6 block" />
          <span className="text-[15px] font-semibold text-foreground tracking-tight leading-none">
            productsense
          </span>
        </div>
      </div>

      <div className="px-3 py-3">
        <button
          onClick={onCreateProject}
          disabled={creating}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium border border-border bg-card hover:bg-muted transition-colors text-foreground disabled:opacity-50"
        >
          <Plus size={13} />
          {creating ? "Creating…" : "New project"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground px-2 mb-2 font-medium">
          Projects
        </p>
        <div className="space-y-1">
          {loading && (
            <p className="px-3 py-2 text-[11px] text-muted-foreground">Loading…</p>
          )}
          {!loading && projects.length === 0 && (
            <p className="px-3 py-2 text-[11px] text-muted-foreground leading-relaxed">
              No projects yet.
            </p>
          )}
          {projects.map((p) => {
            const isActive = activeProjectId === p.id;
            return (
              <div
                key={p.id}
                className={`group w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-all cursor-pointer ${
                  isActive
                    ? "bg-secondary text-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
                onClick={() => onSelectProject(p.id)}
              >
                <span className="text-base shrink-0">{p.icon ?? "📁"}</span>
                <span className="truncate flex-1">{p.name}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${p.name}"? This cannot be undone.`)) {
                      onDeleteProject(p.id);
                    }
                  }}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-rose-700 transition-opacity"
                  title="Delete"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>

      </div>

      <div className="px-3 py-3 border-t border-border">
        <div className="flex items-center gap-2 px-2 py-1">
          <div className="w-7 h-7 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center text-xs font-medium">
            {initial}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-foreground truncate">{username}</p>
            <p className="text-[10px] text-muted-foreground truncate">Free plan</p>
          </div>
          <button
            onClick={() => navigate("/settings")}
            title="Settings"
            className="text-muted-foreground hover:text-foreground p-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <SettingsIcon size={12} />
          </button>
          <button
            onClick={signOut}
            title="Sign out"
            className="text-muted-foreground hover:text-foreground p-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <LogOut size={12} />
          </button>
        </div>
      </div>
    </aside>
  );
}
