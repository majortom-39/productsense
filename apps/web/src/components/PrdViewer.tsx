import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  MessageSquarePlus,
  History,
  ShieldAlert,
  CheckCircle2,
  Sparkles,
  AlertCircle,
  Boxes,
} from "lucide-react";
import type { Prd, Decision, Feature } from "@/lib/api";

interface Props {
  prd: Prd | null;
  decisions: Decision[];
  /** Features — the MVP cut renders at the top of the PRD ("what we're building"). */
  features?: Feature[];
  onAskMaya?: (selectedText: string) => void;
}

interface Section {
  id: string;
  title: string;
  body: string;
}

/** Split a markdown body into top-level sections by H2 (## ...) headings. */
function parseSections(md: string): Section[] {
  if (!md) return [];
  const lines = md.split("\n");
  const sections: Section[] = [];
  let current: { title: string; bodyLines: string[] } | null = null;
  for (const line of lines) {
    const m = line.match(/^##\s+(.+?)\s*$/);
    if (m) {
      if (current) {
        sections.push({ id: slugify(current.title), title: current.title, body: current.bodyLines.join("\n").trim() });
      }
      current = { title: m[1], bodyLines: [] };
    } else if (current) {
      current.bodyLines.push(line);
    }
  }
  if (current) {
    sections.push({ id: slugify(current.title), title: current.title, body: current.bodyLines.join("\n").trim() });
  }
  return sections;
}

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

export function PrdViewer({ prd, decisions, features = [], onAskMaya }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [activeSection, setActiveSection] = useState<string>("");

  const sections = useMemo(() => parseSections(prd?.body_md ?? ""), [prd]);
  const openQuestions = decisions.filter((d) => d.status === "open").length;
  const guardrails = useMemo(
    () => decisions.filter((d) => d.tag === "guardrail" && d.status === "decided"),
    [decisions],
  );
  // The MVP cut: features marked in_mvp. Before the cut, show all features as
  // "proposed" so the founder always sees the scope on the PRD tab.
  const inMvp = useMemo(() => features.filter((f) => f.in_mvp), [features]);
  const mvpFeatures = inMvp.length > 0 ? inMvp : features;
  const mvpPending = inMvp.length === 0 && features.length > 0;

  const projectTitle = useMemo(() => {
    const first = prd?.body_md?.match(/^#\s+(.+?)\s*$/m);
    return first ? first[1] : "Product";
  }, [prd]);

  useEffect(() => {
    if (!sections.length) return;
    if (!activeSection || !sections.find((s) => s.id === activeSection)) {
      setActiveSection(sections[0].id);
    }
  }, [sections, activeSection]);

  useEffect(() => {
    function handleMouseUp() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) return setTooltip(null);
      const text = sel.toString().trim();
      if (text.length < 5) return setTooltip(null);
      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      const cont = containerRef.current?.getBoundingClientRect();
      if (!cont) return;
      setTooltip({ x: rect.left + rect.width / 2 - cont.left, y: rect.top - cont.top - 8, text });
    }
    document.addEventListener("mouseup", handleMouseUp);
    return () => document.removeEventListener("mouseup", handleMouseUp);
  }, []);

  function jumpTo(id: string) {
    setActiveSection(id);
    const el = scrollRef.current?.querySelector(`[data-section="${id}"]`);
    if (el && scrollRef.current) {
      scrollRef.current.scrollTo({ top: (el as HTMLElement).offsetTop - 24, behavior: "smooth" });
    }
  }

  // Truly empty only when there's no PRD, no features, and no guardrails yet.
  if (!prd && mvpFeatures.length === 0 && guardrails.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-6">
        <p className="text-sm font-medium text-foreground">PRD will appear here</p>
        <p className="text-xs text-muted-foreground max-w-[260px] leading-relaxed">
          Maya drafts it as you talk — the MVP feature list, the spec, and the guardrails all live here.
        </p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full flex flex-col relative">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0 gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">prd.md</h3>
          {prd && (openQuestions === 0 ? (
            <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-medium border border-emerald-100 flex items-center gap-1">
              <CheckCircle2 size={9} />
              All sections answered
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 text-[10px] font-medium border border-amber-100 flex items-center gap-1">
              <AlertCircle size={9} />
              {openQuestions} open question{openQuestions === 1 ? "" : "s"}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {guardrails.length > 0 && (
            <span className="px-2.5 py-1 rounded-md text-[10.5px] font-medium bg-rose-50 text-rose-700 border border-rose-100 flex items-center gap-1" title="Guardrails active for this project">
              <ShieldAlert size={10} />
              {guardrails.length} guardrail{guardrails.length === 1 ? "" : "s"}
            </span>
          )}
          {prd && (
            <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 px-2 py-1 rounded-md">
              <History size={11} />
              v{prd.version}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 flex min-h-0">
        {sections.length > 0 && (
          <nav className="w-[200px] flex-shrink-0 border-r border-border overflow-y-auto py-5 px-3 hidden md:block">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2 px-2">Sections</p>
            <ul className="space-y-0.5">
              {sections.map((s, i) => {
                const active = activeSection === s.id;
                return (
                  <li key={s.id}>
                    <button
                      onClick={() => jumpTo(s.id)}
                      className={`w-full text-left px-2 py-1.5 rounded-md text-[11.5px] leading-snug transition-colors flex items-start gap-1.5 ${
                        active ? "bg-secondary text-foreground font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                      }`}
                    >
                      <span className={`text-[10px] font-mono mt-0.5 ${active ? "text-foreground/60" : "text-muted-foreground/60"}`}>
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="flex-1">{s.title}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-[640px] mx-auto">
            <h1 className="text-[22px] font-semibold text-foreground mb-1 leading-tight">{projectTitle}</h1>
            <p className="text-[12px] text-muted-foreground mb-8">
              Product Requirements Document · drafted by Maya{prd ? ` · v${prd.version}` : " (in progress)"}
            </p>

            {/* ── What we're building (MVP) — the feature list at the top ── */}
            {mvpFeatures.length > 0 && (
              <section className="mb-8 rounded-2xl border border-border bg-muted/30 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Boxes size={14} className="text-foreground/70" />
                  <h2 className="text-[14px] font-semibold text-foreground">
                    What we're building {mvpPending ? "(MVP cut pending)" : "(MVP)"}
                  </h2>
                  <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
                    {mvpFeatures.length}
                  </span>
                </div>
                <ul className="space-y-2.5">
                  {mvpFeatures.map((f) => (
                    <li key={f.id} className="flex items-start gap-2.5">
                      <CheckCircle2 size={13} className="text-foreground/40 mt-0.5 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-foreground leading-snug">{f.title}</p>
                        {f.description && (
                          <p className="text-[12px] text-muted-foreground leading-relaxed">{f.description}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* ── The spec ── */}
            {prd && sections.length > 0 ? (
              <div className="space-y-7">
                {sections.map((s) => (
                  <section key={s.id} data-section={s.id} className="group/section">
                    <div className="flex items-center gap-2 mb-2">
                      <h2 className="text-[15px] font-semibold text-foreground">{s.title}</h2>
                      {onAskMaya && (
                        <button
                          onClick={() => onAskMaya(`${s.title}: ${s.body.slice(0, 200)}`)}
                          className="opacity-0 group-hover/section:opacity-100 transition-opacity px-2 py-0.5 rounded-md text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted flex items-center gap-1"
                          title={`Ask Maya about ${s.title}`}
                        >
                          <Sparkles size={10} className="text-primary" />
                          Ask Maya
                        </button>
                      )}
                    </div>
                    <div className="prose prose-warm prose-sm max-w-none text-[13px] leading-relaxed text-foreground/85">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.body}</ReactMarkdown>
                    </div>
                  </section>
                ))}
              </div>
            ) : prd ? (
              <div className="prose prose-warm prose-sm max-w-none text-[13px] leading-relaxed text-foreground/85">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{prd.body_md}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-[12px] text-muted-foreground italic">
                The full spec hasn't been drafted yet — Maya writes it once the scope is settled.
              </p>
            )}

            {/* ── Guardrails / constraints (non-negotiables) ── */}
            {guardrails.length > 0 && (
              <section className="mt-9 rounded-2xl border border-rose-100 bg-rose-50/40 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <ShieldAlert size={14} className="text-rose-700" />
                  <h2 className="text-[14px] font-semibold text-foreground">Guardrails — non-negotiables</h2>
                </div>
                <ul className="space-y-3">
                  {guardrails.map((g) => (
                    <li key={g.id} className="group/g">
                      <div className="flex items-center gap-2">
                        <p className="text-[13px] font-medium text-foreground leading-snug">{g.title}</p>
                        {onAskMaya && (
                          <button
                            onClick={() => onAskMaya(`Guardrail ${g.display_id} — ${g.title}\n\n${g.detail}`)}
                            className="opacity-0 group-hover/g:opacity-100 transition-opacity px-1.5 py-0.5 rounded text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted"
                            title="Ask Maya about this guardrail"
                          >
                            Ask Maya
                          </button>
                        )}
                      </div>
                      {g.detail && <p className="text-[12px] text-muted-foreground leading-relaxed">{g.detail}</p>}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="mt-10 pt-5 border-t border-border text-[11px] text-muted-foreground">
              Want to change something? Select any text above — "Ask Maya" appears.
              Maya is the only editor; changes cascade to the sprint board.
            </div>
          </div>
        </div>
      </div>

      {tooltip && onAskMaya && (
        <button
          style={{ left: tooltip.x, top: tooltip.y, transform: "translate(-50%, -100%)" }}
          className="absolute z-50 px-3 py-2 rounded-xl bg-foreground text-background text-[12px] font-medium shadow-lg flex items-center gap-2 hover:bg-foreground/90"
          onMouseDown={(e) => {
            e.preventDefault();
            onAskMaya(tooltip.text);
            setTooltip(null);
            window.getSelection()?.removeAllRanges();
          }}
        >
          <MessageSquarePlus size={12} />
          Ask Maya about this
        </button>
      )}
    </div>
  );
}
