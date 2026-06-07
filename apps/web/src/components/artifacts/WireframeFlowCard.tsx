/**
 * WireframeFlowCard — renders a Maya-drawn UX flow: a sequence of greyscale
 * screens, each in a device frame, with transition arrows between them and a
 * "derived from research" chip per screen (the traceability half of the spec).
 *
 * Each screen's HTML is rendered inside a no-scripts sandboxed iframe wrapped in
 * the greyscale design system (see wireframe-template.ts). The card chrome uses
 * the app's own neutral tokens so it sits cleanly on the Screens tab.
 */
import { ArrowRight, Link2, Smartphone, Globe, Puzzle, Monitor } from "lucide-react";
import type { WireframeDevice, WireframeFlowPayload, WireframeScreen } from "./types";
import { wireframeDocument } from "./wireframe-template";

// Inner content dimensions per device (the iframe viewport).
const DEVICE_DIMS: Record<WireframeDevice, { w: number; h: number }> = {
  phone: { w: 264, h: 532 },
  browser: { w: 460, h: 300 },
  extension: { w: 320, h: 430 },
  desktop: { w: 560, h: 352 },
};

const DEVICE_ICON: Record<WireframeDevice, React.ReactNode> = {
  phone: <Smartphone size={11} />,
  browser: <Globe size={11} />,
  extension: <Puzzle size={11} />,
  desktop: <Monitor size={11} />,
};

const FLOW_TYPE_LABEL: Record<string, string> = {
  onboarding: "Onboarding",
  core: "Core flow",
  settings: "Settings",
  error: "Error state",
  empty: "Empty state",
  auth: "Auth",
  other: "Flow",
};

/** A row of greyscale "traffic light" dots used in browser/desktop chrome. */
const Dots = () => (
  <div className="flex items-center gap-1.5">
    {[0, 1, 2].map((i) => (
      <span key={i} className="w-2.5 h-2.5 rounded-full bg-foreground/15" />
    ))}
  </div>
);

/** The device chrome wrapping a screen's iframe. */
function DeviceFrame({ device, children }: { device: WireframeDevice; children: React.ReactNode }) {
  const { w } = DEVICE_DIMS[device];

  if (device === "phone") {
    return (
      <div
        className="relative rounded-[2rem] border border-foreground/15 bg-card p-2 shadow-[0_2px_8px_rgba(24,24,27,.08),0_12px_32px_rgba(24,24,27,.06)]"
        style={{ width: w + 16 }}
      >
        <div className="absolute left-1/2 top-2 -translate-x-1/2 z-10 h-5 w-28 rounded-b-2xl bg-foreground/10" />
        <div className="overflow-hidden rounded-[1.5rem] border border-foreground/10">{children}</div>
      </div>
    );
  }

  if (device === "extension") {
    return (
      <div
        className="rounded-xl border border-foreground/15 bg-card shadow-[0_2px_8px_rgba(24,24,27,.08),0_12px_32px_rgba(24,24,27,.06)] overflow-hidden"
        style={{ width: w }}
      >
        <div className="flex items-center justify-between px-3 h-8 border-b border-foreground/10 bg-muted/40">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Extension</span>
          <Dots />
        </div>
        {children}
      </div>
    );
  }

  // browser + desktop share a windowed chrome; browser shows a URL pill.
  return (
    <div
      className="rounded-xl border border-foreground/15 bg-card shadow-[0_2px_8px_rgba(24,24,27,.08),0_12px_32px_rgba(24,24,27,.06)] overflow-hidden"
      style={{ width: w }}
    >
      <div className="flex items-center gap-3 px-3 h-9 border-b border-foreground/10 bg-muted/40">
        <Dots />
        {device === "browser" && (
          <div className="flex-1 h-5 rounded-md bg-background border border-foreground/10" />
        )}
      </div>
      {children}
    </div>
  );
}

function ScreenColumn({
  screen,
  device,
  index,
}: {
  screen: WireframeScreen;
  device: WireframeDevice;
  index: number;
}) {
  const { w, h } = DEVICE_DIMS[device];
  return (
    <figure className="flex flex-col gap-2.5" style={{ width: device === "phone" ? w + 16 : w }}>
      <DeviceFrame device={device}>
        <iframe
          // Sandbox with NO allow-scripts → model HTML can't execute JS.
          sandbox=""
          title={screen.name}
          srcDoc={wireframeDocument(screen.html, device)}
          style={{ width: device === "phone" ? w : "100%", height: h, border: "none", display: "block" }}
        />
      </DeviceFrame>

      <figcaption className="px-0.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
            {String(index + 1).padStart(2, "0")}
          </span>
          <h4 className="text-[13px] font-semibold text-foreground leading-snug">{screen.name}</h4>
        </div>
        {screen.notes && (
          <p className="mt-1 text-[11.5px] text-muted-foreground leading-relaxed">{screen.notes}</p>
        )}
        {screen.derived_from && (
          <span
            title="The feature + friction/pain this screen serves"
            className="mt-2 inline-flex items-start gap-1 rounded-md bg-muted px-2 py-1 text-[10.5px] font-medium text-muted-foreground border border-border max-w-full"
          >
            <Link2 size={10} className="mt-0.5 flex-shrink-0" />
            <span className="leading-snug">{screen.derived_from}</span>
          </span>
        )}
      </figcaption>
    </figure>
  );
}

export function WireframeFlowCard({ payload }: { payload: WireframeFlowPayload }) {
  const { screens, device, flow_name, flow_type, transitions, informed_by } = payload;

  // Map "from→to" to the trigger label so we can annotate the arrow between
  // consecutive screens (the common case: the flow reads left-to-right).
  const triggerFor = (fromName: string, toName: string): string | undefined =>
    transitions?.find((t) => t.from === fromName && t.to === toName)?.trigger;

  return (
    <div className="rounded-2xl border border-border bg-card/40 p-4">
      {(flow_name || flow_type || (informed_by && informed_by.length > 0)) && (
        <header className="mb-4 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-foreground/5 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-foreground border border-foreground/10">
            {DEVICE_ICON[device]}
            {FLOW_TYPE_LABEL[flow_type ?? "other"]}
          </span>
          {flow_name && (
            <h3 className="text-[14px] font-semibold text-foreground leading-snug">{flow_name}</h3>
          )}
          {informed_by && informed_by.length > 0 && (
            <span className="ml-auto inline-flex items-center gap-1 text-[10.5px] text-muted-foreground">
              <Link2 size={10} />
              {informed_by.length} research link{informed_by.length === 1 ? "" : "s"}
            </span>
          )}
        </header>
      )}

      <div className="flex items-start gap-1 overflow-x-auto pb-2">
        {screens.map((screen, i) => (
          <div key={`${screen.name}-${i}`} className="flex items-start gap-1">
            <ScreenColumn screen={screen} device={device} index={i} />
            {i < screens.length - 1 && (
              <div className="flex flex-col items-center justify-center self-stretch px-2 pt-16 text-muted-foreground">
                <ArrowRight size={18} className="flex-shrink-0" />
                {(() => {
                  const trig = triggerFor(screen.name, screens[i + 1].name);
                  return trig ? (
                    <span className="mt-1 max-w-[80px] text-center text-[9.5px] leading-tight text-muted-foreground/80">
                      {trig}
                    </span>
                  ) : null;
                })()}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
