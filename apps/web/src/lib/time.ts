/**
 * Time formatting for the UI.
 *
 * Scope note (founder hard rule): ProductSense never shows agent-invented
 * *timelines or effort estimates* — "this'll take 2 weeks", "≈2 days", story
 * points, velocity. Vibe coding has no such schedule, so we don't fabricate one.
 *
 * A FACTUAL recency stamp on a real artifact ("created 3h ago") is a different
 * thing — it's a fact about the record, not a prediction — and is allowed.
 * That's what this helper is for. Keep it to recency of things that actually
 * happened; never use it to imply how long something *will* take.
 */

/** "just now" / "5m ago" / "3h ago" / "2d ago", then an absolute short date
 *  past a week. Returns "" for missing/invalid input. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
