/**
 * ScreensTab — the founder's view of the UX flows Maya has drawn.
 *
 * Each card is a `wireframe_flow` discovery artifact: a greyscale screen flow
 * rendered through the ArtifactRenderer (→ WireframeFlowCard). Read-only;
 * "Add to chat" quotes a flow back to Maya for refinement.
 */
import { useMemo } from "react";
import { Layout, MessageSquarePlus } from "lucide-react";
import type { DiscoveryArtifact } from "@/lib/api";
import { ArtifactRenderer } from "@/components/artifacts";

interface Props {
  items: DiscoveryArtifact[];
  onAddToChat?: (quoted: string) => void;
}

function flowToQuote(card: DiscoveryArtifact): string {
  const parts = [`Screen flow · ${card.title}`];
  if (card.summary && card.summary.trim()) parts.push(card.summary.trim());
  return parts.join("\n");
}

export function ScreensTab({ items, onAddToChat }: Props) {
  // Oldest first — flows read in the order Maya built them.
  const flows = useMemo(
    () =>
      [...items].sort(
        (a, b) =>
          new Date(a.created_at ?? 0).getTime() - new Date(b.created_at ?? 0).getTime(),
      ),
    [items],
  );

  if (flows.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 py-4 border-b border-border flex-shrink-0">
          <h3 className="text-sm font-semibold text-foreground">Screens</h3>
        </div>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center max-w-sm">
            <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
              <Layout size={20} className="text-muted-foreground" />
            </div>
            <p className="text-[13px] font-medium text-foreground/85 mb-1.5">No screens yet</p>
            <p className="text-[12px] text-muted-foreground leading-relaxed">
              Once you've agreed the MVP, Maya will talk through the flow with you and
              then draw the screens here — each element tied back to a feature and the
              friction it removes.
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
          <h3 className="text-sm font-semibold text-foreground">Screens</h3>
          <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
            {flows.length} {flows.length === 1 ? "flow" : "flows"}
          </span>
        </div>
        <p className="text-[10.5px] text-muted-foreground italic">
          Greyscale wireframes · read-only — discuss changes with Maya
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
        {flows.map((flow) => (
          <section key={flow.id}>
            <header className="flex items-start justify-between gap-3 mb-3">
              <div className="min-w-0">
                <h3 className="text-[14px] font-semibold text-foreground leading-snug">{flow.title}</h3>
                {flow.summary && (
                  <p className="mt-0.5 text-[12px] text-foreground/75 leading-relaxed">{flow.summary}</p>
                )}
              </div>
              {onAddToChat && (
                <button
                  onClick={() => onAddToChat(flowToQuote(flow))}
                  title="Quote this flow in chat — Maya can refine or redraw it"
                  className="flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <MessageSquarePlus size={11} />
                  Add to chat
                </button>
              )}
            </header>
            <ArtifactRenderer render_kind={flow.render_kind} payload={flow.payload} textBody={flow.summary} />
          </section>
        ))}
      </div>
    </div>
  );
}
