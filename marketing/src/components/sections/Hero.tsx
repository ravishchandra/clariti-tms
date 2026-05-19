import Link from "next/link";
import { LocaleCycler } from "./LocaleCycler";
import { Reveal } from "../Reveal";

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden">
      <div className="absolute inset-0 grid-bg" aria-hidden />
      <div className="absolute inset-x-0 top-0 -z-10 h-[600px] bg-gradient-to-b from-[var(--color-flame)]/[0.045] to-transparent" />

      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-12 px-6 pt-20 pb-24 lg:grid-cols-12 lg:gap-8 lg:pt-28">
        <div className="lg:col-span-7">
          <Reveal>
            <Link
              href="/#how-it-works"
              className="group inline-flex items-center gap-2 rounded-full border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/60 px-3 py-1 text-[11.5px] tracking-tight text-[var(--color-text-soft)] backdrop-blur transition-colors hover:border-[var(--color-flame)]/40 hover:text-white"
            >
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-flame)] pulse-dot" />
              <span className="font-mono uppercase tracking-[0.14em] text-[10px] text-[var(--color-flame-soft)]">
                v0.7
              </span>
              <span>Phases 1–6 + XLIFF, OTA, screenshot SDK shipped</span>
              <span className="text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </Link>
          </Reveal>

          <Reveal delay={80}>
            <h1 className="mt-7 text-balance text-[44px] font-bold leading-[1.02] tracking-[-0.045em] text-[var(--color-text)] sm:text-[56px] lg:text-[68px]">
              The translation system{" "}
              <span className="gradient-text-flame">you actually own.</span>
            </h1>
          </Reveal>

          <Reveal delay={140}>
            <p className="mt-6 max-w-xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
              Clariti is a self-hosted TMS that runs your strings through a context-aware LLM
              pipeline — your provider, your data, your prompts. Open source. No seat tax. No
              vendor lock-in.
            </p>
          </Reveal>

          <Reveal delay={210}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href="/playground"
                className="group inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[14px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] hover:-translate-y-px"
              >
                Try the playground
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </Link>
              <Link
                href="/#install"
                className="group inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/70 px-4 py-2.5 text-[14px] font-medium text-[var(--color-text)] backdrop-blur transition-all hover:border-[var(--color-flame)]/45"
              >
                <span className="font-mono text-[12px] text-[var(--color-flame-soft)]">$</span>
                <span className="font-mono">loc demo</span>
                <span className="text-[var(--color-text-muted)]">— no API keys</span>
              </Link>
            </div>
          </Reveal>

          <Reveal delay={260}>
            <dl className="mt-12 grid max-w-lg grid-cols-3 gap-x-4 gap-y-3 border-t border-[var(--color-line)]/70 pt-6">
              <Stat k="0" v="vendor lock-in" />
              <Stat k="10%" v="of Lokalise pricing*" />
              <Stat k="100%" v="of your data" />
            </dl>
          </Reveal>
        </div>

        <div className="lg:col-span-5">
          <Reveal delay={120}>
            <LocaleCycler />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="font-mono text-[20px] font-medium leading-none tracking-tight text-[var(--color-flame-soft)]">
        {k}
      </dt>
      <dd className="mt-1.5 text-[11.5px] uppercase tracking-[0.08em] text-[var(--color-text-muted)]">
        {v}
      </dd>
    </div>
  );
}
