/**
 * wireframe-template.ts — the document scaffold every Maya-drawn screen is
 * rendered inside.
 *
 * Maya authors only the *structural* HTML for a screen body (semantic tags
 * and/or the `wf-*` utility classes below). We wrap it in this full HTML
 * document — a deliberate **greyscale design system** with real contrast and a
 * proper type scale — and hand it to a no-scripts sandboxed iframe. The result
 * reads like a designer's greyscale wireframe, not a raw HTML dump, no matter
 * how plain the markup Maya writes.
 *
 * Greyscale on purpose: wireframes communicate structure + hierarchy + intent,
 * never brand colour. One restrained accent (ink) carries primary actions.
 */
import type { WireframeDevice } from "./types";

/** Base body font-size per device — phones read larger relative to their frame. */
const DEVICE_BASE_PX: Record<WireframeDevice, number> = {
  phone: 15,
  browser: 14,
  extension: 13.5,
  desktop: 14,
};

const DESIGN_SYSTEM_CSS = `
  /* ── Greyscale tokens — high-contrast, single ink accent ───────────── */
  :root {
    --ink:        #18181b;   /* near-black: text + primary fills */
    --ink-soft:   #3f3f46;   /* secondary text */
    --muted:      #71717a;   /* tertiary text, captions */
    --faint:      #a1a1aa;   /* placeholders, disabled */
    --line:       #d4d4d8;   /* borders */
    --line-soft:  #e4e4e7;   /* hairlines, dividers */
    --surface:    #ffffff;   /* cards, sheets */
    --bg:         #f4f4f5;   /* page background */
    --bg-sunken:  #ececee;   /* wells, image placeholders */
    --radius:     12px;
    --radius-sm:  8px;
    --radius-pill: 999px;
    --shadow:     0 1px 2px rgba(24,24,27,.06), 0 4px 16px rgba(24,24,27,.05);
    --shadow-sm:  0 1px 2px rgba(24,24,27,.07);
    --gap:        16px;
    --font: ui-sans-serif, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", system-ui, sans-serif;
    --mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Code", Menlo, monospace;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    font-family: var(--font);
    color: var(--ink);
    background: var(--bg);
    line-height: 1.45;
    letter-spacing: -0.006em;
    padding: 20px;
    min-height: 100%;
    /* subtle paper grain so empty space doesn't read as "broken/blank" */
    background-image: radial-gradient(rgba(24,24,27,.025) 0.5px, transparent 0.5px);
    background-size: 14px 14px;
  }

  /* ── Type scale ────────────────────────────────────────────────────── */
  h1 { font-size: 1.6rem;  font-weight: 680; letter-spacing: -0.02em; line-height: 1.15; }
  h2 { font-size: 1.25rem; font-weight: 660; letter-spacing: -0.015em; line-height: 1.2; }
  h3 { font-size: 1.02rem; font-weight: 640; letter-spacing: -0.01em; }
  h4 { font-size: 0.84rem; font-weight: 640; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
  p  { color: var(--ink-soft); }
  small, .wf-caption { font-size: 0.78rem; color: var(--muted); }
  a { color: var(--ink); text-decoration: underline; text-underline-offset: 2px; }
  strong { font-weight: 640; color: var(--ink); }
  h1+p, h2+p, h3+p { margin-top: 6px; }
  * + h2, * + h3 { margin-top: 22px; }
  * + p, * + ul, * + ol { margin-top: 10px; }

  /* ── Layout helpers ────────────────────────────────────────────────── */
  .wf-stack > * + * { margin-top: var(--gap); }
  .wf-row  { display: flex; align-items: center; gap: 12px; }
  .wf-between { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .wf-grid { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
  .wf-spacer { flex: 1; }

  /* ── Components ─────────────────────────────────────────────────────── */
  button, .wf-btn {
    font: inherit; font-weight: 600; cursor: pointer;
    padding: 11px 18px; border-radius: var(--radius-sm);
    background: var(--ink); color: #fff; border: 1px solid var(--ink);
    letter-spacing: -0.01em; box-shadow: var(--shadow-sm);
  }
  .wf-btn--ghost, button.ghost {
    background: var(--surface); color: var(--ink); border: 1px solid var(--line);
    box-shadow: none;
  }
  .wf-btn--block { display: block; width: 100%; text-align: center; }

  input, textarea, select, .wf-input {
    font: inherit; width: 100%; color: var(--ink);
    padding: 11px 14px; border: 1px solid var(--line); border-radius: var(--radius-sm);
    background: var(--surface);
  }
  input::placeholder, textarea::placeholder { color: var(--faint); }
  label { display: block; font-size: 0.8rem; font-weight: 600; color: var(--ink-soft); margin-bottom: 6px; }

  .wf-card {
    background: var(--surface); border: 1px solid var(--line-soft);
    border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow);
  }

  ul, ol { padding-left: 1.1rem; color: var(--ink-soft); }
  li + li { margin-top: 6px; }
  .wf-list { list-style: none; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; background: var(--surface); }
  .wf-list > li { display: flex; align-items: center; gap: 12px; padding: 13px 15px; margin: 0; }
  .wf-list > li + li { border-top: 1px solid var(--line-soft); }

  .wf-appbar, header.wf-appbar {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 12px 4px 16px; font-weight: 660; font-size: 1.05rem;
  }
  .wf-tabbar {
    display: flex; justify-content: space-around; gap: 4px;
    border-top: 1px solid var(--line); padding-top: 12px; margin-top: 22px;
    color: var(--muted); font-size: 0.72rem; text-align: center;
  }
  .wf-tabbar .active { color: var(--ink); font-weight: 640; }

  .wf-chip, .badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: var(--radius-pill);
    background: var(--bg-sunken); color: var(--ink-soft);
    font-size: 0.74rem; font-weight: 600; border: 1px solid var(--line-soft);
  }

  .wf-avatar { width: 38px; height: 38px; border-radius: 50%; background: var(--bg-sunken); border: 1px solid var(--line); flex: none; }
  .wf-img, .wf-thumb {
    background: var(--bg-sunken); border: 1px solid var(--line-soft); border-radius: var(--radius-sm);
    min-height: 96px; display: flex; align-items: center; justify-content: center;
    color: var(--faint); font-size: 0.74rem; font-weight: 600;
    /* diagonal "image placeholder" cross-hatch */
    background-image:
      linear-gradient(45deg, var(--line-soft) 1px, transparent 1px),
      linear-gradient(-45deg, var(--line-soft) 1px, transparent 1px);
    background-size: 18px 18px;
  }
  .wf-fab {
    position: fixed; right: 20px; bottom: 20px; width: 52px; height: 52px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; box-shadow: var(--shadow);
  }
  hr, .wf-divider { border: none; border-top: 1px solid var(--line-soft); margin: 18px 0; }
  code, .wf-mono { font-family: var(--mono); font-size: 0.85em; }
`;

/**
 * Wrap a screen's body HTML in the full greyscale document. Returned string is
 * dropped into an iframe `srcDoc`. No scripts run (the iframe is sandboxed
 * without `allow-scripts`), so this is safe for model-authored markup.
 */
export function wireframeDocument(bodyHtml: string, device: WireframeDevice): string {
  const basePx = DEVICE_BASE_PX[device] ?? 14;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>html{font-size:${basePx}px;}${DESIGN_SYSTEM_CSS}</style>
</head>
<body>
${bodyHtml || '<div class="wf-img" style="min-height:160px">empty screen</div>'}
</body>
</html>`;
}
