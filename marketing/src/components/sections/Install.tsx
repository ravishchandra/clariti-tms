import Link from "next/link";
import { Reveal } from "../Reveal";
import { site } from "@/lib/site";

const lines: { p: string; c: string; o?: string }[] = [
  { p: "$", c: "git clone " + "github.com/clariti-tms/clariti" },
  { p: "$", c: "docker compose up -d postgres" },
  { p: "$", c: "pip install -e \".[dev]\" && cd infra && alembic upgrade head" },
  { p: "$", c: "loc demo --locale fr-FR", o: "ok · 5 strings translated · 4 approved · 1 needs_review" },
];

export function Install() {
  return (
    <section id="install" className="relative">
      <div className="mx-auto max-w-7xl px-6 py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-5">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Self-host in five minutes
              </p>
              <h2 className="mt-4 text-balance text-[40px] font-[450] leading-[1.08] tracking-[-0.02em] sm:text-[52px]">
                One Postgres. One CLI. Zero API keys to start.
              </h2>
              <p className="mt-5 text-pretty text-[17px] leading-[1.7] text-[var(--color-text-soft)]">
                The <span className="font-mono text-[var(--color-text)]">loc demo</span> command
                spins a fresh project, ingests five sample strings, and walks them through the full
                pipeline with a mock provider — no API keys, no signup. Swap in your own provider
                when you are ready to translate real work.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link
                  href="/playground"
                  className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#ffffff] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] hover:-translate-y-px"
                >
                  Skip the install — try the playground →
                </Link>
                <a
                  href={`${site.github}#readme`}
                  className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] transition-all hover:border-[var(--color-flame)]/40"
                >
                  Read the docs
                </a>
              </div>
            </Reveal>
          </div>

          <div className="lg:col-span-7">
            <Reveal delay={120}>
              <div className="theme-dark rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/95 shadow-2xl backdrop-blur-md">
                <div className="flex items-center justify-between border-b border-[var(--color-line)]/80 px-4 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
                  </div>
                  <div className="font-mono text-[11px] text-[var(--color-text-muted)]">
                    ~/clariti — zsh
                  </div>
                  <div className="font-mono text-[11px] text-[var(--color-text-muted)]">
                    ⌘+t
                  </div>
                </div>
                <div className="px-5 py-5 font-mono text-[12.5px] leading-[1.75]">
                  {lines.map((l, i) => (
                    <div key={i}>
                      <div className="flex items-baseline gap-2">
                        <span className="text-[var(--color-flame-soft)]">{l.p}</span>
                        <span className="text-[var(--color-text)]">{l.c}</span>
                      </div>
                      {l.o && (
                        <div className="pl-4 text-[var(--color-text-muted)]">
                          <span className="text-[var(--color-mint)]">✓</span> {l.o}
                        </div>
                      )}
                    </div>
                  ))}
                  <div className="flex items-baseline gap-2">
                    <span className="text-[var(--color-flame-soft)]">$</span>
                    <span className="caret" />
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}
