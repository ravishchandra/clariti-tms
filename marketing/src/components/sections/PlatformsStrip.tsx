import { Reveal } from "../Reveal";

const platforms: { name: string; formats: string; path: string }[] = [
  {
    name: "iOS",
    formats: ".strings · .xcstrings · .stringsdict",
    path: "App/{locale}.lproj/Localizable.strings",
  },
  {
    name: "Android",
    formats: "strings.xml + <plurals> + CLDR",
    path: "res/values-{android_tag}/strings.xml",
  },
  {
    name: "React / TypeScript",
    formats: "i18next namespace JSON · ICU",
    path: "locales/{locale}/{namespace}.json",
  },
  {
    name: "Flutter",
    formats: ".arb · @key metadata round-trip",
    path: "lib/l10n/app_{locale}.arb",
  },
];

export function PlatformsStrip() {
  return (
    <section
      aria-label="Supported platforms"
      className="relative border-y border-[var(--color-line)]/70 bg-[var(--color-ink-1)]/40"
    >
      <div className="mx-auto max-w-7xl px-6 py-14">
        <Reveal>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
              Works with
            </p>
            <p className="text-[14px] text-[var(--color-text-soft)]">
              Platform-native file formats. No rewrite of your i18n setup. Translated files
              land where your build already looks for them.
            </p>
          </div>
        </Reveal>
        <Reveal delay={80}>
          <div className="mt-7 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
            {platforms.map((p) => (
              <div
                key={p.name}
                className="rounded-lg border border-[var(--color-line)]/80 bg-[var(--color-ink-0)]/60 p-4 transition-colors hover:border-[var(--color-flame)]/35"
              >
                <div className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
                  {p.name}
                </div>
                <div className="mt-1.5 font-mono text-[11px] leading-relaxed text-[var(--color-text-soft)]">
                  {p.formats}
                </div>
                <div className="mt-2.5 font-mono text-[10.5px] leading-relaxed text-[var(--color-text-muted)]">
                  {p.path}
                </div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
