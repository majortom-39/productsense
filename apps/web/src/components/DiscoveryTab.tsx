/**
 * DiscoveryTab — the founder's view of every artifact Maya has synthesized
 * for the project.
 *
 * A flat, chronological feed of finished cards (no stages, no placeholders).
 * Each card renders through the kind-specific ArtifactRenderer (persona cards,
 * charts, tables, mermaid, etc.), falling back to a text card otherwise.
 * Read-only — "Add to chat" is the only direct action; everything else flows
 * through conversation with Maya.
 */
import { useMemo } from "react";
import { Layers, MessageSquarePlus, Pin, Users, Wand2 } from "lucide-react";
import type { DiscoveryArtifact, RenderKind } from "@/lib/api";
import { timeAgo } from "@/lib/time";
import { ArtifactRenderer } from "@/components/artifacts";

// Human label for the render kind (chip text). Falls back to render_kind
// itself for shapes we don't have a special label for.
const KIND_LABEL: Record<string, string> = {
  persona_cards: "Personas",
  stack_diagram: "Stack",
  matrix: "Matrix",
  bar_chart: "Chart",
  line_chart: "Chart",
  graph: "Graph",
  mermaid: "Diagram",
  table: "Table",
  text: "Note",
};

const SOURCE_AGENT_LABELS: Record<string, string> = {
  iris: "Iris",
  aiden: "Aiden",
  hugo: "Hugo",
  zara: "Zara",
  theo: "Theo",
  nora: "Nora",
  kai: "Kai",
  wes: "Wes",
};

// ─── Helpers ─────────────────────────────────────────────────────────

function sourceAgentsOf(card: DiscoveryArtifact): string[] {
  const meta = card.metadata as { source_agents?: unknown } | null | undefined;
  const raw = meta?.source_agents;
  if (!Array.isArray(raw)) return [];
  return raw.filter((x): x is string => typeof x === "string" && x.length > 0);
}

function artifactToQuote(card: DiscoveryArtifact): string {
  const parts = [`Discovery card · ${card.title} (${card.render_kind})`];
  if (card.summary && card.summary.trim()) parts.push(card.summary.trim());
  return parts.join("\n");
}

// ─── Sub-components ──────────────────────────────────────────────────

const KindChip: React.FC<{ kind: RenderKind | string }> = ({ kind }) => {
  const label = KIND_LABEL[kind] ?? kind;
  return (
    <span className="px-2 py-0.5 rounded-md text-[10px] font-medium uppercase tracking-wider text-muted-foreground bg-muted border border-border">
      {label}
    </span>
  );
};

const ProvenanceBadge: React.FC<{ card: DiscoveryArtifact }> = ({ card }) => {
  if (card.created_by === "maya_synthesized") {
    return (
      <span
        title="Synthesized by Maya from research findings"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-violet-50 text-violet-700 text-[10px] font-medium border border-violet-100"
      >
        <Wand2 size={9} />
        Synthesized
      </span>
    );
  }
  return (
    <span
      title="Pinned by Maya from a sub-agent run"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-medium border border-emerald-100"
    >
      <Pin size={9} />
      Pinned
    </span>
  );
};

const SourceAgentsBadge: React.FC<{ agents: string[] }> = ({ agents }) => {
  if (agents.length === 0) return null;
  const pretty = agents.map((a) => SOURCE_AGENT_LABELS[a] ?? a).join(" + ");
  return (
    <span
      title={`Research from ${pretty}`}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 text-[10px] font-medium border border-amber-100"
    >
      <Users size={9} />
      {pretty}
    </span>
  );
};

// ─── Card ────────────────────────────────────────────────────────────

interface CardProps {
  card: DiscoveryArtifact;
  onAddToChat?: (quoted: string) => void;
}

/** A discovery card. The kind-specific renderer drives the body. */
const ArtifactCard: React.FC<CardProps> = ({ card, onAddToChat }) => {
  const sourceAgents = sourceAgentsOf(card);
  return (
    <article className="rounded-2xl border border-border bg-card p-4 transition-colors hover:border-border/80">
      <header className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <h3 className="text-[13.5px] font-semibold text-foreground leading-snug mb-0.5">
            {card.title}
          </h3>
          <p className="text-[10.5px] text-muted-foreground">
            {timeAgo(card.updated_at ?? card.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0 flex-wrap justify-end">
          <SourceAgentsBadge agents={sourceAgents} />
          <KindChip kind={card.render_kind} />
          <ProvenanceBadge card={card} />
        </div>
      </header>

      {card.summary && card.render_kind !== "text" && (
        <p className="text-[12px] text-foreground/75 leading-relaxed mb-3">
          {card.summary}
        </p>
      )}

      <ArtifactRenderer
        render_kind={card.render_kind}
        payload={card.payload}
        textBody={card.summary}
      />

      {onAddToChat && (
        <div className="flex items-center justify-end pt-3 mt-3 border-t border-border">
          <button
            onClick={() => onAddToChat(artifactToQuote(card))}
            title="Quote this card in chat — Maya can refine, refresh, or rebuild it"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <MessageSquarePlus size={11} />
            Add to chat
          </button>
        </div>
      )}
    </article>
  );
};

// ─── Main component ──────────────────────────────────────────────────

interface Props {
  items: DiscoveryArtifact[];
  /** Triggered by a card's "Add to chat" button — quotes the card into
   *  the chat input so the founder can ask Maya about it. */
  onAddToChat?: (quoted: string) => void;
}

export function DiscoveryTab({ items, onAddToChat }: Props) {
  // Oldest first — the founder reads the project chronologically.
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      const at = new Date(a.created_at ?? 0).getTime();
      const bt = new Date(b.created_at ?? 0).getTime();
      return at - bt;
    });
  }, [items]);

  // Empty state — no scaffolding, no placeholders.
  if (sorted.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Discovery</h3>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center max-w-sm">
            <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
              <Layers size={20} className="text-muted-foreground" />
            </div>
            <p className="text-[13px] font-medium text-foreground/85 mb-1.5">
              Nothing here yet
            </p>
            <p className="text-[12px] text-muted-foreground leading-relaxed">
              As you and Maya work through the project, the discoveries she
              pins or synthesizes will land here.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">Discovery</h3>
          <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
            {sorted.length} {sorted.length === 1 ? "card" : "cards"}
          </span>
        </div>
        <p className="text-[10.5px] text-muted-foreground italic">
          Oldest first · read-only — discuss changes with Maya
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-3">
        {sorted.map((card) => (
          <ArtifactCard key={card.id} card={card} onAddToChat={onAddToChat} />
        ))}
      </div>
    </div>
  );
}
