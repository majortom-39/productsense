import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

interface Props {
  onSend: (text: string) => void;
  awaitingInput?: boolean;
  isStreaming?: boolean;
  prefillText?: string | null;
  onPrefillConsumed?: () => void;
}

export function ChatInput({
  onSend,
  awaitingInput = true,
  isStreaming = false,
  prefillText,
  onPrefillConsumed,
}: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!prefillText) return;
    setText(`> "${prefillText}"\n\n`);
    ref.current?.focus();
    onPrefillConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillText]);

  function handleSend() {
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <div className="px-5 pb-5 pt-2">
      <div className="flex items-end gap-2 border border-border rounded-2xl px-3 py-2 bg-card">
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          placeholder={
            isStreaming ? "Maya is thinking…" : awaitingInput ? "Reply to Maya…" : "Message Maya…"
          }
          className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none leading-relaxed max-h-32 py-1.5 px-1"
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() || isStreaming}
          className="p-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-30 transition"
        >
          <ArrowUp size={14} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}
