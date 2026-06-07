import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as Msg } from "@/hooks/useMayaSession";
import { markdownComponentsWithMermaid } from "@/components/markdownComponents";

export function ChatMessage({ message }: { message: Msg }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted/40 text-foreground border border-border"
        }`}
      >
        {!isUser && (
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Maya
          </p>
        )}
        <div className="prose prose-sm dark:prose-invert max-w-none [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponentsWithMermaid}>
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
