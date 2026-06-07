/**
 * TextCard — markdown body. Used as the fallback when render_kind isn't
 * recognised or when a structured payload fails to parse.
 *
 * For artifacts produced by Maya/sub-agents with render_kind='text', the
 * body usually arrives via `summary` (Maya's pin) or `finding` (sub-agent).
 * The dispatcher decides which source to pass in.
 *
 * Inline Mermaid: any markdown code block tagged `mermaid` is rendered as
 * a diagram inline. Maya can drop a ```mermaid ... ``` block in any text
 * artifact (or in chat prose via the same component) and it draws.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponentsWithMermaid } from "@/components/markdownComponents";

interface Props {
  body?: string | null;
  /** When true, render a tiny "couldn't render" hint above the body. Set
   *  by the dispatcher when it fell back to text because the structured
   *  payload was malformed. */
  degraded?: boolean;
}

export function TextCard({ body, degraded }: Props) {
  const text = (body ?? "").trim();
  if (!text && !degraded) {
    return (
      <p className="text-[12px] text-muted-foreground italic">No content.</p>
    );
  }
  return (
    <div className="space-y-2">
      {degraded && (
        <p className="text-[10.5px] uppercase tracking-wider text-amber-700 font-medium">
          Showing as text — original structured payload couldn't be rendered.
        </p>
      )}
      {text && (
        <div className="prose prose-sm max-w-none text-foreground/85 prose-p:leading-relaxed prose-li:leading-relaxed prose-headings:font-semibold prose-headings:text-foreground prose-strong:text-foreground prose-strong:font-semibold prose-a:text-primary prose-a:no-underline hover:prose-a:underline">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponentsWithMermaid}>{text}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
