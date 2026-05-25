import { cn } from "@/lib/utils";

/**
 * Editorial page header used across all dashboard pages.
 *
 * Mirrors the typographic rhythm of the marketing site's section heads —
 * mono-eyebrow → confident-but-uncrowded h1 (Geist Variable, font-[450],
 * tight tracking) → soft body text. Optional right-side `actions` slot
 * for primary CTAs without disturbing the eyebrow / title alignment.
 *
 * Reference: marketing/src/components/sections/Hero.tsx, Pillars.tsx,
 * Install.tsx — same eyebrow → headline → body pattern at a larger scale.
 */
export function PageHeader({
  eyebrow,
  title,
  body,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  body?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex items-start justify-between gap-6 flex-wrap",
        className,
      )}
    >
      <div className="flex flex-col gap-2 min-w-0 flex-1">
        {eyebrow ? <p className="mono-eyebrow">{eyebrow}</p> : null}
        <h1 className="text-balance text-[30px] font-[450] leading-[1.1] tracking-[-0.018em] text-foreground sm:text-[34px]">
          {title}
        </h1>
        {body ? (
          <p className="mt-1 text-pretty text-[14.5px] leading-[1.6] text-text-soft max-w-prose">
            {body}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2 shrink-0">{actions}</div> : null}
    </header>
  );
}

/**
 * Shared page shell — generous padding + max-width to give the dashboard
 * the same editorial breathing room as the marketing site, scaled down
 * for an interior tool (px-8 py-10 vs marketing's px-6 py-24).
 */
export function PageShell({
  children,
  className,
  size = "default",
}: {
  children: React.ReactNode;
  className?: string;
  size?: "default" | "wide" | "narrow";
}) {
  return (
    <div
      className={cn(
        "px-6 py-10 sm:px-8 sm:py-12 flex flex-col gap-8",
        size === "wide" && "max-w-6xl",
        size === "narrow" && "max-w-2xl",
        size === "default" && "max-w-5xl",
        className,
      )}
    >
      {children}
    </div>
  );
}
