/**
 * Shared react-markdown `components` config — intercepts ```mermaid blocks
 * and renders them as diagrams inline. Reused by:
 *   - TextCard (Research / chat artifact text)
 *   - ChatPanel assistant prose
 *   - ChatMessage (legacy chat row, kept for back-compat)
 *
 * Centralising this means a single change touches everywhere markdown
 * renders — no risk of one surface drawing diagrams and another not.
 */
import type { Components } from "react-markdown";
import { MermaidCard } from "@/components/artifacts/MermaidCard";

/** react-markdown v10 dropped the `inline` flag on the `code` component
 *  signature. Detect by className presence — a fenced block carries
 *  `language-foo`; bare inline code has no className. Cheap, reliable. */
export const markdownComponentsWithMermaid: Components = {
  code({ className, children, ...rest }) {
    const text = String(children ?? "").replace(/\n$/, "");
    const lang = /language-(\w+)/.exec(className ?? "")?.[1];
    const isFenced = !!className && /language-\w+/.test(className);
    if (isFenced && lang === "mermaid" && text.trim()) {
      return <MermaidCard payload={{ source: text }} />;
    }
    return (
      <code className={className} {...rest}>
        {children}
      </code>
    );
  },
};
