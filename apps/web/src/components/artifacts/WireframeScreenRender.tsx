/**
 * WireframeScreenRender — draws a screen DETERMINISTICALLY from typed blocks.
 *
 * Maya emits structured blocks (see types.ts `WireframeBlock`); this component
 * owns all layout, spacing, and typography via the scoped greyscale design
 * system in wireframe.css. No model-authored HTML, no iframe — so every screen
 * is consistent and mid-fidelity regardless of how the model fills the content.
 *
 * Skeleton: [status bar (phone)] → [app bar] → [scrollable body] → [bottom bar].
 * The body grows and scrolls; the bottom bar pins — which is what kills the
 * "floating content + dead space" problem of the old free-HTML approach.
 */
import type {
  WireframeBlock,
  WireframeDevice,
  WireframeScreen,
} from "./types";
import "./wireframe.css";

function StatusBar() {
  return (
    <div className="wf-statusbar">
      <span>9:41</span>
      <span className="wf-sb-right">
        <span className="wf-sb-dot" />
        <span className="wf-sb-glyph" />
        <span className="wf-sb-glyph wf-sb-batt" />
      </span>
    </div>
  );
}

function AppBar({ bar }: { bar: NonNullable<WireframeScreen["appBar"]> }) {
  const leading = bar.leading && bar.leading !== "none" ? bar.leading : null;
  return (
    <div className="wf-appbar">
      {leading === "back" && (
        <span className="wf-ab-icon">
          <span className="wf-glyph-back" />
        </span>
      )}
      {leading === "menu" && (
        <span className="wf-ab-icon">
          <span className="wf-glyph-menu" />
        </span>
      )}
      <span className={`wf-ab-title${!leading && !(bar.trailing?.length) ? " wf-center" : ""}`}>
        {bar.title ?? ""}
      </span>
      {bar.trailing && bar.trailing.length > 0 && (
        <span className="wf-ab-trail">
          {bar.trailing.map((t, i) => (
            <span key={i} className="wf-ab-pill">{t}</span>
          ))}
        </span>
      )}
    </div>
  );
}

function BottomBar({ bar }: { bar: NonNullable<WireframeScreen["bottomBar"]> }) {
  if (bar.kind === "nav") {
    return (
      <div className="wf-bottombar wf-nav">
        {bar.items.map((it, i) => (
          <span key={i} className={`wf-nav-item${it.active ? " wf-active" : ""}`}>
            <span className="wf-nav-icon" />
            {it.label}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div className="wf-bottombar wf-actions">
      {bar.buttons.map((b, i) => (
        <span key={i} className={`wf-btn${b.variant === "secondary" ? " wf-secondary" : ""}`}>
          {b.label}
        </span>
      ))}
    </div>
  );
}

function Block({ block }: { block: WireframeBlock }) {
  switch (block.type) {
    case "heading":
      return <div className={`wf-h wf-h${block.level ?? 2}`}>{block.text}</div>;
    case "text":
      return <p className={`wf-p${block.tone === "muted" ? " wf-muted" : ""}`}>{block.text}</p>;
    case "input": {
      const kind = block.kind ?? "text";
      return (
        <div>
          {block.label && <span className="wf-label">{block.label}</span>}
          {kind === "search" ? (
            <div className="wf-input wf-search">
              <span className="wf-search-dot" />
              {block.placeholder ?? "Search"}
            </div>
          ) : (
            <div className={`wf-input${kind === "textarea" ? " wf-area" : ""}`}>
              {kind === "password" ? "••••••••" : block.placeholder ?? ""}
            </div>
          )}
        </div>
      );
    }
    case "button":
      return (
        <span className={`wf-btn${block.variant === "secondary" ? " wf-secondary" : ""}${block.fullWidth ? " wf-block" : ""}`}>
          {block.label}
        </span>
      );
    case "buttonGroup":
      return (
        <div className={`wf-btngroup ${block.layout === "row" ? "wf-row" : "wf-stack"}`}>
          {block.buttons.map((b, i) => (
            <span key={i} className={`wf-btn${b.variant === "secondary" ? " wf-secondary" : ""}`}>
              {b.label}
            </span>
          ))}
        </div>
      );
    case "list":
      return (
        <ul className="wf-list">
          {block.items.map((it, i) => (
            <li key={i}>
              {it.leading && (
                <span className={`wf-li-lead${it.leading === "avatar" ? " wf-avatar" : ""}`} />
              )}
              <span className="wf-li-body">
                <span className="wf-li-title">{it.title}</span>
                {it.subtitle && <span className="wf-li-sub">{it.subtitle}</span>}
              </span>
              {it.trailing && <span className="wf-li-trail">{it.trailing}</span>}
            </li>
          ))}
        </ul>
      );
    case "card":
      return (
        <div className="wf-card">
          {block.title && <div className="wf-card-title">{block.title}</div>}
          {block.body && <div className="wf-card-body">{block.body}</div>}
          {block.chips && block.chips.length > 0 && (
            <div className="wf-chips" style={{ marginTop: 10 }}>
              {block.chips.map((c, i) => (
                <span key={i} className="wf-chip">{c}</span>
              ))}
            </div>
          )}
        </div>
      );
    case "image": {
      const ratio = block.ratio ?? "wide";
      return (
        <div className={`wf-ph wf-${ratio}${ratio === "wide" ? "" : " wf-min"}`}>
          {block.label ?? "image"}
        </div>
      );
    }
    case "media": {
      const v = block.variant ?? "image";
      if (v === "audio") {
        return (
          <div className="wf-media">
            <span className="wf-wave">
              {[10, 18, 26, 14, 22, 8, 16, 24, 12, 20, 9, 17].map((h, i) => (
                <span key={i} style={{ height: h }} />
              ))}
            </span>
            {block.label ?? "audio"}
          </div>
        );
      }
      if (v === "video") {
        return <div className="wf-media"><span className="wf-play" />{block.label ?? "video"}</div>;
      }
      if (v === "map") {
        return <div className="wf-media wf-map">{block.label}</div>;
      }
      return <div className="wf-ph wf-min">{block.label ?? "image"}</div>;
    }
    case "chips":
      return (
        <div className="wf-chips">
          {block.items.map((c, i) => (
            <span key={i} className="wf-chip">{c}</span>
          ))}
        </div>
      );
    case "metricRow":
      return (
        <div className="wf-metrics">
          {block.metrics.map((m, i) => (
            <div key={i} className="wf-metric">
              <div className="wf-metric-val">{m.value}</div>
              {m.label && <div className="wf-metric-lab">{m.label}</div>}
            </div>
          ))}
        </div>
      );
    case "field":
      return (
        <div className="wf-field">
          <span className="wf-field-lab">{block.label}</span>
          {block.value && <span className="wf-field-val">{block.value}</span>}
        </div>
      );
    case "toggleRow":
      return (
        <div className="wf-toggle">
          <span className="wf-toggle-lab">{block.label}</span>
          <span className={`wf-switch${block.on ? " wf-on" : ""}`} />
        </div>
      );
    case "segmented":
      return (
        <div className="wf-seg">
          {block.options.map((o, i) => (
            <span key={i} className={`wf-seg-opt${(block.active ?? 0) === i ? " wf-active" : ""}`}>
              {o}
            </span>
          ))}
        </div>
      );
    case "hero":
      return (
        <div className="wf-hero">
          {block.media && <div className="wf-hero-media" />}
          {block.kicker && <div className="wf-hero-kicker">{block.kicker}</div>}
          <div className="wf-hero-title">{block.title}</div>
          {block.subtitle && <div className="wf-hero-sub">{block.subtitle}</div>}
        </div>
      );
    case "divider":
      return <hr className="wf-divider" />;
    case "spacer":
      return <div className={`wf-spacer wf-${block.size ?? "md"}`} />;
    default:
      return null;
  }
}

export function WireframeScreenRender({
  screen,
  device,
}: {
  screen: WireframeScreen;
  device: WireframeDevice;
}) {
  return (
    <div className="wf-screen">
      {device === "phone" && <StatusBar />}
      {screen.appBar && <AppBar bar={screen.appBar} />}
      <div className="wf-body">
        {(screen.blocks ?? []).map((b, i) => (
          <Block key={i} block={b} />
        ))}
      </div>
      {screen.bottomBar && <BottomBar bar={screen.bottomBar} />}
    </div>
  );
}
