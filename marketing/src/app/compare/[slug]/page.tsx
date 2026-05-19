import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Reveal } from "@/components/Reveal";
import { competitors, getCompetitor } from "@/lib/competitors";
import { site } from "@/lib/site";
import { cn } from "@/lib/cn";

export function generateStaticParams() {
  return competitors.map((c) => ({ slug: c.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const c = getCompetitor(slug);
  if (!c) return {};
  const title = `${c.tagline} — open-source, self-hosted, BYO-LLM`;
  const description = c.intro.slice(0, 220);
  return {
    title,
    description,
    alternates: { canonical: `/compare/${c.slug}` },
    openGraph: { title, description },
    keywords: [
      `${c.name} alternative`,
      `${c.name} vs Clariti`,
      `open source ${c.name} alternative`,
      `self-hosted ${c.name} alternative`,
      `${c.name} pricing`,
      "translation management system",
      "TMS comparison",
    ],
  };
}

export default async function CompareCompetitorPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const c = getCompetitor(slug);
  if (!c) notFound();

  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: c.faqs.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
      <Nav />
      <main>
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-20 pb-12 lg:pt-28">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Comparison
              </p>
              <h1 className="mt-4 max-w-4xl text-balance text-[42px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[56px]">
                Clariti TMS <span className="text-[var(--color-text-muted)]">vs</span>{" "}
                <span className="gradient-text-flame">{c.name}</span>
              </h1>
              <p className="mt-5 max-w-3xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
                {c.oneLiner}
              </p>
            </Reveal>

            <Reveal delay={120}>
              <div className="mt-8 grid max-w-3xl grid-cols-1 gap-px overflow-hidden rounded-xl bg-[var(--color-line)]/70 ring-line sm:grid-cols-3">
                <Stat k="Free" v="self-host, AGPL-3.0" accent />
                <Stat k="BYO LLM" v="Claude, GPT, DeepL, Ollama" />
                <Stat k={c.pricingHook.split(" ").slice(0, 2).join(" ")} v={c.pricingHook} />
              </div>
            </Reveal>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-12">
            <Reveal>
              <p className="text-pretty text-[16px] leading-[1.7] text-[var(--color-text-soft)]">
                {c.intro}
              </p>
            </Reveal>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <h2 className="text-balance text-[28px] font-semibold tracking-[-0.025em]">
                Feature-by-feature
              </h2>
            </Reveal>
            <Reveal delay={100}>
              <div className="mt-8 overflow-x-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-1)]/70">
                <table className="w-full min-w-[720px] border-separate border-spacing-0 text-[13.5px]">
                  <thead>
                    <tr>
                      <th className="border-b border-[var(--color-line)] px-5 py-4 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                        Capability
                      </th>
                      <th className="border-b border-[var(--color-line)] bg-[var(--color-flame)]/[0.08] px-5 py-4 text-left text-[12px] font-semibold text-[var(--color-flame-soft)]">
                        Clariti TMS
                      </th>
                      <th className="border-b border-[var(--color-line)] px-5 py-4 text-left text-[12px] font-semibold text-[var(--color-text-soft)]">
                        {c.name}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.features.map((f) => (
                      <tr key={f.label}>
                        <th
                          scope="row"
                          className="border-b border-[var(--color-line)]/60 px-5 py-4 text-left align-top font-medium text-[var(--color-text)]"
                        >
                          {f.label}
                          {f.hint && (
                            <div className="mt-0.5 text-[12px] font-normal text-[var(--color-text-muted)]">
                              {f.hint}
                            </div>
                          )}
                        </th>
                        <td
                          className={cn(
                            "border-b border-[var(--color-line)]/60 bg-[var(--color-flame)]/[0.04] px-5 py-4 align-top",
                            f.winner === "clariti" && "text-[var(--color-text)]",
                          )}
                        >
                          {f.winner === "clariti" && <WinBadge />}
                          <div
                            className={cn(
                              "text-[13.5px] leading-relaxed",
                              f.winner === "clariti"
                                ? "text-[var(--color-text)]"
                                : "text-[var(--color-text-soft)]",
                            )}
                          >
                            {f.clariti}
                          </div>
                        </td>
                        <td className="border-b border-[var(--color-line)]/60 px-5 py-4 align-top">
                          {f.winner === "them" && <WinBadge muted />}
                          <div className="text-[13.5px] leading-relaxed text-[var(--color-text-soft)]">
                            {f.them}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Reveal>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <div className="grid grid-cols-1 gap-12 lg:grid-cols-2">
              <Reveal>
                <h3 className="text-[22px] font-semibold tracking-tight">
                  When to keep {c.name}
                </h3>
                <ul className="mt-5 space-y-3">
                  {c.whenThem.map((w) => (
                    <li
                      key={w}
                      className="flex items-start gap-2.5 text-[14.5px] leading-[1.6] text-[var(--color-text-soft)]"
                    >
                      <span className="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-muted)]" />
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>

              <Reveal delay={80}>
                <h3 className="text-[22px] font-semibold tracking-tight text-[var(--color-flame-soft)]">
                  When Clariti wins
                </h3>
                <ul className="mt-5 space-y-3">
                  {c.whenClariti.map((w) => (
                    <li
                      key={w}
                      className="flex items-start gap-2.5 text-[14.5px] leading-[1.6] text-[var(--color-text)]"
                    >
                      <span className="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-flame)]" />
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
            </div>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-16">
            <Reveal>
              <h2 className="text-[28px] font-semibold tracking-[-0.025em]">
                Migrating from {c.name} to Clariti
              </h2>
              <p className="mt-3 max-w-3xl text-[15px] leading-[1.7] text-[var(--color-text-soft)]">
                The export-and-import path is short. Most teams run both systems for one release
                cycle, compare output, and cut the {c.name} contract at renewal.
              </p>
            </Reveal>
            <ol className="mt-8 space-y-5">
              {c.migration.map((m, i) => (
                <Reveal key={m.step} delay={i * 60}>
                  <li className="flex gap-5">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] font-mono text-[12px] text-[var(--color-flame-soft)]">
                      {String(i + 1).padStart(2, "0")}
                    </div>
                    <div>
                      <div className="text-[16px] font-semibold tracking-tight text-[var(--color-text)]">
                        {m.step}
                      </div>
                      <p className="mt-1 text-[14.5px] leading-[1.6] text-[var(--color-text-soft)]">
                        {m.body}
                      </p>
                    </div>
                  </li>
                </Reveal>
              ))}
            </ol>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-16">
            <Reveal>
              <h2 className="text-[28px] font-semibold tracking-[-0.025em]">
                FAQ — Clariti vs {c.name}
              </h2>
            </Reveal>
            <div className="mt-8 divide-y divide-[var(--color-line)]/70 border-y border-[var(--color-line)]/70">
              {c.faqs.map((f) => (
                <details key={f.q} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-baseline justify-between gap-6 text-[16px] font-medium tracking-tight text-[var(--color-text)] transition-colors hover:text-white">
                    <span className="text-pretty">{f.q}</span>
                    <span className="font-mono text-[18px] text-[var(--color-flame-soft)] transition-transform group-open:rotate-45">
                      +
                    </span>
                  </summary>
                  <p className="mt-4 max-w-3xl text-pretty text-[14.5px] leading-[1.7] text-[var(--color-text-soft)]">
                    {f.a}
                  </p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 pb-24">
            <Reveal>
              <div className="rounded-xl border border-[var(--color-flame)]/25 bg-[var(--color-ink-1)]/80 p-8 sm:p-10">
                <h2 className="text-balance text-[24px] font-semibold tracking-tight sm:text-[28px]">
                  Try Clariti against your real strings in 5 minutes.
                </h2>
                <p className="mt-3 max-w-2xl text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                  No signup, no API keys, no credit card. <span className="font-mono">loc demo</span>{" "}
                  ships a full translation round-trip with a mock provider so you can see the
                  pipeline before you wire up Claude or GPT-4.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    href="/playground"
                    className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)]"
                  >
                    Try the playground →
                  </Link>
                  <Link
                    href="/pricing"
                    className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] transition-all hover:border-[var(--color-flame)]/40 hover:text-white"
                  >
                    See pricing
                  </Link>
                  <Link
                    href="/#compare"
                    className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] transition-all hover:border-[var(--color-flame)]/40 hover:text-white"
                  >
                    Compare all
                  </Link>
                </div>
              </div>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

function Stat({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <div className={cn("bg-[var(--color-ink-1)] px-5 py-4", accent && "bg-[var(--color-flame)]/[0.06]")}>
      <div
        className={cn(
          "font-mono text-[16px] font-medium tracking-tight",
          accent ? "text-[var(--color-flame-soft)]" : "text-[var(--color-text)]",
        )}
      >
        {k}
      </div>
      <div className="mt-1 text-[12px] leading-snug text-[var(--color-text-muted)]">{v}</div>
    </div>
  );
}

function WinBadge({ muted }: { muted?: boolean }) {
  return (
    <div
      className={cn(
        "mb-1.5 inline-flex items-center gap-1 rounded font-mono text-[9.5px] uppercase tracking-[0.12em]",
        muted ? "text-[var(--color-text-muted)]" : "text-[var(--color-flame-soft)]",
      )}
    >
      <span>{muted ? "→" : "★"}</span>
      <span>{muted ? "their pick" : "our pick"}</span>
    </div>
  );
}
