# Design Tokens — ProductSense v1

> **Note:** This is the v1-locked design system. The earlier Anthropic-warm-parchment palette from `Productsense v.0` is the inspiration but **not** the active spec. v1 ships on a near-white canvas with soft near-black text.

## Palette (hard-locked)

| Token | Hex | Where |
|---|---|---|
| **Background** | `#FCFCFB` | Page canvas. Warm-tinted near-white. |
| **Foreground** | `#212121` | All primary text. Soft near-black, never pure black. |
| **Card surface** | `#FFFFFF` | Pure white for slight elevation above the canvas. |
| **Brand / primary CTA** | `#c96442` | Terracotta. ONLY for primary CTAs and the brand mark. |
| **Coral accent** | `#d97757` | Lighter brand variant. |
| **Warm sand (secondary)** | `#e8e6dc` | Secondary button surface. |
| **Border cream** | `#f0eee6` | Standard border on light surfaces. |
| **Border warm** | `#e8e6dc` | Emphasized borders, dividers. |
| **Olive gray** | `#5e5d59` | Secondary body text. |
| **Stone gray** | `#87867f` | Tertiary text, metadata. |
| **Charcoal warm** | `#4d4c48` | Text on warm-sand buttons. |
| **Focus blue** | `#3898ec` | Input focus rings only. The only cool color. |

## Status tints (used very sparingly)

| Tone | Tailwind | Meaning |
|---|---|---|
| Emerald | `bg-emerald-50 text-emerald-700` | Fresh / approved / done |
| Amber | `bg-amber-50 text-amber-700` | Needs attention / open question / stale |
| Violet | `bg-violet-50 text-violet-700` | Maya-flavored (autonomous decisions, "from Maya") |
| Blue | `bg-blue-50 text-blue-700` | Agent-flavored (in-progress, IDE-resolved decisions) |
| Rose | `bg-rose-50 text-rose-700` | Guardrails / "do not" |

CTAs always use brand terracotta — status tints are background tints, not action colors.

## Typography

- **Body / UI:** `Inter` 400/500. Relaxed line-height (1.55–1.65) on body, tighter (1.10–1.30) on headings.
- **Headlines:** Inter 500/600 — no serif fallback in v1 (the Anthropic Serif from v.0 was inspiration, not active spec).
- **Code / mono:** any monospace, used only for code, IDs, file names, agent names in chips.

## Radius scale

- 4–6px — small inline elements (badges, status pills)
- 8px — standard cards, secondary buttons
- 12px — primary buttons, input fields
- 16px — featured containers
- 24–32px — large rounded shells (the workspace card uses `rounded-3xl`)

## Shadows

- **Ring** — `0 0 0 1px <warm gray>` for hover/focus on interactive cards.
- **Whisper** — `rgba(0,0,0,0.05) 0 4px 24px` for floating panels and modals.
- No drop shadows beyond whisper. Depth comes from background/foreground contrast.

## Anti-patterns (don't do)

- ❌ Cool blue-grays (except focus blue).
- ❌ Bold (700+) on body text.
- ❌ Pure black `#000` anywhere — always soft `#212121`.
- ❌ Saturated colors beyond terracotta.
- ❌ Sharp corners (< 6px radius) on buttons or cards.
- ❌ Heavy drop shadows.
- ❌ Pure white background (`#FFFFFF`) — always the warm-tinted `#FCFCFB`.

## Quick reference for prompts

When asking an agent to design a component:
- *"On `#FCFCFB` background with `#212121` text"*
- *"Card on `#FFFFFF` with `1px solid #f0eee6` border, `rounded-2xl`"*
- *"Primary button: `bg-primary` (`#c96442`), `text-primary-foreground`, `rounded-xl`"*
- *"Secondary button: outline, `border-border`, `bg-card`, `hover:bg-muted`"*
