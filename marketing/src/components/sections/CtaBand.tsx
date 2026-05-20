import Link from "next/link";
import { Reveal } from "../Reveal";

export function CtaBand() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-7xl px-6 pb-8 pt-4">
        <Reveal>
          <div className="relative overflow-hidden rounded-2xl border border-[var(--color-flame)]/25 bg-gradient-to-br from-[var(--color-ink-1)] to-[var(--color-ink-2)] p-10 sm:p-14">
            <div className="absolute inset-0 grid-bg opacity-50" aria-hidden />
            <div className="absolute -right-32 top-1/2 h-[300px] w-[300px] -translate-y-1/2 rounded-full bg-[var(--color-flame)]/[0.18] blur-3xl" />
            <div className="relative flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-end">
              <div className="max-w-2xl">
                <h2 className="text-balance text-[32px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[40px]">
                  Stop renting the bundle.{" "}
                  <span className="gradient-text-flame">Own the pipeline.</span>
                </h2>
                <p className="mt-4 text-pretty text-[17px] leading-[1.7] text-[var(--color-text-soft)]">
                  Five minutes from <span className="font-mono">git clone</span> to a French
                  translation that actually sounds French.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link
                  href="/playground"
                  className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-5 py-3 text-[14px] font-semibold text-[#ffffff] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] hover:-translate-y-px"
                >
                  Try the playground
                  <span>→</span>
                </Link>
                <Link
                  href="/agents"
                  className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/80 px-5 py-3 text-[14px] font-medium text-[var(--color-text)] backdrop-blur transition-all hover:border-[var(--color-flame)]/45"
                >
                  Drop into Claude Code, Cursor, Cline
                </Link>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
