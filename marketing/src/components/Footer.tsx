import Link from "next/link";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { site } from "@/lib/site";

const columns = [
  {
    title: "Product",
    links: [
      { href: "/#features", label: "Features" },
      { href: "/#how-it-works", label: "How it works" },
      { href: "/#compare", label: "Compare" },
      { href: "/pricing", label: "Pricing" },
    ],
  },
  {
    title: "Compare",
    links: [
      { href: "/compare/lokalise", label: "vs Lokalise" },
      { href: "/compare/phrase", label: "vs Phrase" },
      { href: "/compare/crowdin", label: "vs Crowdin" },
    ],
  },
  {
    title: "Open source",
    links: [
      { href: site.github, label: "GitHub", external: true },
      { href: `${site.github}/blob/main/LICENSE`, label: "AGPL-3.0 license", external: true },
      { href: `${site.github}/blob/main/CONTRIBUTING.md`, label: "Contribute", external: true },
      { href: `${site.github}/blob/main/SECURITY.md`, label: "Security policy", external: true },
    ],
  },
  {
    title: "Docs",
    links: [
      { href: `${site.github}#readme`, label: "Quickstart", external: true },
      { href: `${site.github}/blob/main/docs/05-llm-translation-pipeline.md`, label: "LLM pipeline", external: true },
      { href: `${site.github}/blob/main/docs/04-data-model.md`, label: "Data model", external: true },
      { href: `${site.github}/blob/main/docs/12-ota.md`, label: "OTA delivery", external: true },
    ],
  },
];

export function Footer() {
  return (
    <footer className="relative mt-32 border-t border-[var(--color-line)]/70">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid grid-cols-2 gap-12 md:grid-cols-6">
          <div className="col-span-2">
            <Logo />
            <p className="mt-4 max-w-xs text-sm text-[var(--color-text-muted)]">
              The translation management system you actually own. Self-hosted, AGPL, bring-your-own LLM.
            </p>
            <div className="mt-6 flex gap-3 text-[var(--color-text-muted)]">
              <a
                href={site.github}
                aria-label="GitHub"
                className="rounded p-1 transition-colors hover:text-[var(--color-text)]"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
                  <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2 .37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
                </svg>
              </a>
            </div>
          </div>

          {columns.map((col) => (
            <div key={col.title}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                {col.title}
              </div>
              <ul className="mt-3 space-y-2 text-sm">
                {col.links.map((l) => (
                  <li key={l.href + l.label}>
                    {"external" in l && l.external ? (
                      <a
                        href={l.href}
                        className="text-[var(--color-text-soft)] transition-colors hover:text-[var(--color-text)]"
                        target="_blank"
                        rel="noreferrer"
                      >
                        {l.label}
                      </a>
                    ) : (
                      <Link
                        href={l.href}
                        className="text-[var(--color-text-soft)] transition-colors hover:text-[var(--color-text)]"
                      >
                        {l.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-[var(--color-line)]/60 pt-6 text-[12px] text-[var(--color-text-muted)] md:flex-row md:items-center">
          <div>
            © {new Date().getFullYear()} ClaritiTMS contributors. Released under the AGPL-3.0.
          </div>
          <div className="flex items-center gap-4">
            <div className="font-mono text-[11px]">
              <span className="text-[var(--color-flame)]">●</span> all systems operational
            </div>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </footer>
  );
}
