import { showcaseLocales } from "@/lib/site";

export function LanguageMarquee() {
  const items = [...showcaseLocales, ...showcaseLocales];
  return (
    <section
      aria-label="Supported languages"
      className="relative border-y border-[var(--color-line)]/70 bg-[var(--color-ink-1)]/40"
    >
      <div className="pointer-events-none absolute inset-y-0 left-0 w-32 bg-gradient-to-r from-[var(--color-ink-0)] to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-32 bg-gradient-to-l from-[var(--color-ink-0)] to-transparent" />
      <div className="overflow-hidden py-5">
        <div className="flex w-max marquee gap-10 whitespace-nowrap">
          {items.map((l, i) => (
            <div
              key={l.code + i}
              className="flex items-center gap-2 font-mono text-[12.5px]"
            >
              <span className="text-[var(--color-flame)]">·</span>
              <span className="text-[var(--color-text-muted)]">{l.code}</span>
              <span className="text-[var(--color-text-soft)]">{l.native}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
