import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Reveal } from "@/components/Reveal";
import { changelog, changelogStats } from "@/lib/changelog";
import { cn } from "@/lib/cn";

export const metadata: Metadata = {
  title: "Changelog — what shipped, in order",
  description:
    "Real shipping cadence for ClaritiTMS. From initial scaffold to MVP-complete in three days, then weekly updates. Sourced from git, not from a marketing calendar.",
  alternates: { canonical: "/changelog" },
};

const tagStyle: Record<string, string> = {
  phase: "text-[var(--color-flame-soft)] border-[var(--color-flame)]/35 bg-[var(--color-flame)]/10",
  feature: "text-[var(--color-mint)] border-[var(--color-mint)]/35 bg-[var(--color-mint)]/10",
  infra: "text-[var(--color-iris)] border-[var(--color-iris)]/35 bg-[var(--color-iris)]/10",
  docs: "text-[var(--color-text-soft)] border-[var(--color-line-strong)] bg-[var(--color-ink-2)]",
  fix: "text-[var(--color-rose)] border-[var(--color-rose)]/35 bg-[var(--color-rose)]/10",
  security: "text-[var(--color-rose)] border-[var(--color-rose)]/35 bg-[var(--color-rose)]/10",
};

const grouped = changelog.reduce<Record<string, typeof changelog>>((acc, e) => {
  (acc[e.date] ||= []).push(e);
  return acc;
}, {});
const dates = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

export default function ChangelogPage() {
  return (
    <>
      <Nav />
      <main>
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-20 pb-12 lg:pt-28">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Changelog
              </p>
              <h1 className="mt-4 max-w-3xl text-balance text-[44px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[52px]">
                What shipped, in order.
              </h1>
              <p className="mt-5 max-w-2xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
                Pulled from <span className="font-mono text-[var(--color-text)]">git log</span>,
                not a marketing calendar. Each entry maps to merged commits on{" "}
                <span className="font-mono text-[var(--color-text)]">main</span>. If you want
                day-by-day detail, the commits are public.
              </p>
            </Reveal>

            <Reveal delay={120}>
              <dl className="mt-10 grid max-w-2xl grid-cols-2 gap-x-4 gap-y-3 border-t border-[var(--color-line)] pt-6 sm:grid-cols-4">
                <Stat k={String(changelogStats.daysShipping)} v="days from scaffold to MVP" />
                <Stat k={changelogStats.phasesShipped} v="phases shipped" />
                <Stat k={String(changelogStats.commitsTotal)} v="commits on main" />
                <Stat k={changelogStats.filesChanged} v="files touched" />
              </dl>
            </Reveal>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-4xl px-6 py-12">
            <div className="relative">
              <div
                className="absolute left-[7px] top-2 bottom-2 w-px bg-gradient-to-b from-transparent via-[var(--color-line-strong)] to-transparent"
                aria-hidden
              />
              {dates.map((d) => (
                <div key={d} className="relative pb-12">
                  <Reveal>
                    <div className="mb-6 flex items-center gap-3">
                      <span className="z-10 inline-block h-[14px] w-[14px] rounded-full border-2 border-[var(--color-ink-0)] bg-[var(--color-flame)] shadow-flame" />
                      <span className="font-mono text-[12px] uppercase tracking-[0.12em] text-[var(--color-text-soft)]">
                        {formatDate(d)}
                      </span>
                    </div>
                  </Reveal>

                  <div className="ml-7 space-y-4">
                    {grouped[d].map((e, idx) => (
                      <Reveal key={e.title} delay={idx * 40}>
                        <article className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-1)] p-5 transition-colors hover:border-[var(--color-line-strong)]">
                          <div className="flex flex-wrap items-baseline gap-2.5">
                            {e.tag && (
                              <span
                                className={cn(
                                  "rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]",
                                  tagStyle[e.tag] ?? tagStyle.docs,
                                )}
                              >
                                {e.tag}
                              </span>
                            )}
                            <h2 className="text-[17px] font-semibold tracking-tight text-[var(--color-text)]">
                              {e.title}
                            </h2>
                          </div>
                          <p className="mt-2 text-[14.5px] leading-[1.6] text-[var(--color-text-soft)]">
                            {e.body}
                          </p>
                        </article>
                      </Reveal>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-4xl px-6 pb-24">
            <Reveal>
              <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-1)]/70 p-6 text-center">
                <p className="text-[14px] text-[var(--color-text-soft)]">
                  Want the next changelog in your inbox?{" "}
                  <Link href="/agents" className="text-[var(--color-flame-soft)] underline-offset-4 hover:underline">
                    Or wire it into your agent →
                  </Link>
                </p>
              </div>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="font-mono text-[20px] font-medium leading-none tracking-tight text-[var(--color-flame-soft)]">
        {k}
      </dt>
      <dd className="mt-1.5 text-[11.5px] uppercase tracking-[0.08em] text-[var(--color-text-muted)]">{v}</dd>
    </div>
  );
}

function formatDate(iso: string) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}
