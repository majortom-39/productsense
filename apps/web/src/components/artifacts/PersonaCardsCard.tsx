/**
 * PersonaCardsCard — Zara's natural shape. Each persona gets a card with
 * name + role, behavioural traits, a representative quote, and pain
 * points. Renders as a responsive grid (1 column on narrow, 2 columns
 * when the container has room).
 */
import { Quote, User } from "lucide-react";
import type { PersonaCardsPayload } from "./types";

export function PersonaCardsCard({ payload }: { payload: PersonaCardsPayload }) {
  const { personas } = payload;
  if (personas.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Zara returned no personas.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {personas.map((p, i) => (
        <article
          key={i}
          className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-2.5"
        >
          <header className="flex items-center gap-2">
            <span className="w-7 h-7 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center flex-shrink-0">
              <User size={13} />
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-foreground leading-tight truncate">
                {p.name}
              </div>
              {p.role && (
                <div className="text-[11px] text-muted-foreground truncate">
                  {p.role}
                </div>
              )}
            </div>
          </header>

          {p.traits && p.traits.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {p.traits.map((t, j) => (
                <span
                  key={j}
                  className="px-1.5 py-0.5 rounded bg-muted text-[10.5px] text-foreground/75 border border-border"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {p.quote && (
            <blockquote className="text-[11.5px] italic text-foreground/75 leading-relaxed pl-2 border-l-2 border-violet-200 flex gap-1.5">
              <Quote size={10} className="flex-shrink-0 mt-0.5 text-violet-400" />
              <span>{p.quote}</span>
            </blockquote>
          )}

          {p.pains && p.pains.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1">
                Pain points
              </p>
              <ul className="space-y-1">
                {p.pains.map((pain, j) => (
                  <li
                    key={j}
                    className="text-[11.5px] text-foreground/80 leading-relaxed pl-2.5 relative"
                  >
                    <span className="absolute left-0 top-1.5 w-1 h-1 rounded-full bg-rose-400" />
                    {pain}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
