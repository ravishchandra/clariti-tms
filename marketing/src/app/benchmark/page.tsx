import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Reveal } from "@/components/Reveal";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: "Benchmark — measuring product-UI translation quality honestly",
  description:
    "Our methodology for comparing Clariti against Lokalise AI, Phrase NextMT, Crowdin AI, and Google Translate on real product-UI strings, scored by native-speaker raters. Designed to be replicable and unkind to ourselves where we deserve it.",
  alternates: { canonical: "/benchmark" },
  keywords: [
    "translation quality benchmark",
    "TMS comparison",
    "Lokalise AI quality",
    "Phrase NextMT quality",
    "Crowdin AI quality",
    "LLM translation evaluation",
    "back-translation similarity",
  ],
};

const dimensions = [
  {
    name: "Naturalness",
    desc: "Does the translation read like something a native speaker would write? Scored 1–5 by a native rater unaware of which system produced the output.",
  },
  {
    name: "Consistency",
    desc: "Does it stay aligned with the project glossary, brand-locked terms, and prior translations in the same screen? Measured by glossary-adherence rate + cross-string term consistency.",
  },
  {
    name: "Accuracy",
    desc: "Does it preserve the source meaning, placeholders, ICU plural shape, and length budget? Rater-scored 1–5 plus an automated placeholder/ICU integrity check.",
  },
  {
    name: "Back-translation similarity",
    desc: "Cosine similarity between the source sentence and its back-translation, embedded via a multilingual sentence encoder. Catches semantic drift the rater might miss.",
  },
];

const systems = [
  { id: "clariti", label: "Clariti (Claude)", note: "claude-sonnet-4 + back-translation QA + glossary + TM" },
  { id: "lokalise-ai", label: "Lokalise AI", note: "vendor default, glossary uploaded" },
  { id: "phrase-nextmt", label: "Phrase NextMT", note: "vendor default" },
  { id: "crowdin-ai", label: "Crowdin AI", note: "vendor default" },
  { id: "google-mt", label: "Google Translate v3", note: "raw API, no glossary" },
  { id: "deepl", label: "DeepL", note: "raw API, no glossary" },
];

const corpus = [
  { id: "checkout", label: "E-commerce checkout (mobile)", strings: 47, source: "Shopify Polaris Mobile UI strings, public" },
  { id: "fintech-tx", label: "Fintech transactions list (mobile)", strings: 38, source: "Open-source fintech reference app" },
  { id: "saas-onboarding", label: "SaaS onboarding (web)", strings: 53, source: "Open-source admin template" },
  { id: "support-form", label: "Customer support form (web)", strings: 29, source: "Public open-source support kit" },
];

const locales = ["fr-FR", "de-DE", "ja-JP", "es-MX", "pt-BR", "ar-SA", "ko-KR", "hi-IN"];

export default function BenchmarkPage() {
  return (
    <>
      <Nav />
      <main>
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-20 pb-10 lg:pt-28">
            <Reveal>
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/70 px-3 py-1 text-[11.5px]">
                <span className="font-mono uppercase tracking-[0.14em] text-[10px] text-[var(--color-flame-soft)]">
                  in progress
                </span>
                <span className="text-[var(--color-text-soft)]">
                  Methodology published · results land 2026 Q3
                </span>
              </div>
            </Reveal>

            <Reveal delay={80}>
              <h1 className="mt-7 max-w-4xl text-balance text-[44px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[56px]">
                How well does any TMS actually translate{" "}
                <span className="gradient-text-flame">product UI?</span>
              </h1>
            </Reveal>

            <Reveal delay={140}>
              <p className="mt-6 max-w-2xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
                Nobody publishes this. Every vendor claims &ldquo;industry-leading AI
                translation&rdquo; with no numbers to back it. So we are running the comparison
                ourselves — Clariti against Lokalise AI, Phrase NextMT, Crowdin AI, raw Google
                Translate, and raw DeepL — on real product-UI strings, scored by native-speaker
                raters who don&rsquo;t know which system produced which output.
              </p>
            </Reveal>

            <Reveal delay={210}>
              <div className="mt-9 flex flex-wrap gap-3">
                <a
                  href={`${site.github}/issues/new?title=%5Bbenchmark%5D+`}
                  className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[14px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] hover:-translate-y-px"
                >
                  Get notified when results land →
                </a>
                <Link
                  href="/playground"
                  className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] px-4 py-2.5 text-[14px] font-medium text-[var(--color-text)] hover:border-[var(--color-flame)]/45"
                >
                  Try the pipeline →
                </Link>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Why */}
        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-16">
            <Reveal>
              <p className="text-pretty text-[16.5px] leading-[1.7] text-[var(--color-text-soft)]">
                The reason there is no good public benchmark is that running one is annoying:
                you need real strings (not toy sentences), real glossaries, native raters across
                eight or ten locales, and a willingness to publish numbers where your own product
                doesn&rsquo;t win. We are committing to all four, including the last one. If
                Phrase outperforms Clariti on Korean fintech strings, that&rsquo;s a number that
                should be public and a defect we should fix.
              </p>
            </Reveal>
          </div>
        </section>

        {/* Methodology */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Methodology
              </p>
              <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                Four scoring dimensions. Blind raters. Replicable corpus.
              </h2>
            </Reveal>

            <div className="mt-10 grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-[var(--color-line)] ring-line md:grid-cols-2">
              {dimensions.map((d) => (
                <Reveal key={d.name} className="bg-[var(--color-ink-1)] p-6">
                  <div className="text-[16px] font-semibold tracking-tight">{d.name}</div>
                  <p className="mt-2 text-[14px] leading-[1.6] text-[var(--color-text-soft)]">{d.desc}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* Corpus */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Corpus
              </p>
              <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                167 strings · 4 product domains · 8 locales · 6 systems
              </h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                Every string is drawn from a publicly-available open-source app so the corpus is
                inspectable. We publish the full source file alongside the results.
              </p>
            </Reveal>

            <Reveal delay={100}>
              <div className="mt-8 overflow-hidden rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-1)]/70">
                <table className="w-full text-[13.5px]">
                  <thead>
                    <tr className="border-b border-[var(--color-line)] text-left text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                      <th className="px-5 py-3 font-medium">Domain</th>
                      <th className="px-5 py-3 font-medium">Strings</th>
                      <th className="px-5 py-3 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {corpus.map((c) => (
                      <tr key={c.id} className="border-b border-[var(--color-line)]/60 last:border-0">
                        <td className="px-5 py-3.5 font-medium text-[var(--color-text)]">{c.label}</td>
                        <td className="px-5 py-3.5 font-mono text-[var(--color-text-soft)]">{c.strings}</td>
                        <td className="px-5 py-3.5 text-[var(--color-text-soft)]">{c.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Reveal>

            <Reveal delay={140}>
              <div className="mt-6 flex flex-wrap items-center gap-2 text-[13px] text-[var(--color-text-soft)]">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                  locales
                </span>
                {locales.map((l) => (
                  <code
                    key={l}
                    className="rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-2 py-0.5 font-mono text-[12px]"
                  >
                    {l}
                  </code>
                ))}
              </div>
            </Reveal>
          </div>
        </section>

        {/* Systems */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Systems under test
              </p>
              <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                Vendor defaults, with their own glossary upload where supported.
              </h2>
              <p className="mt-3 max-w-2xl text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                We do not tune vendor settings for them. Every system runs out-of-the-box with the
                same glossary file uploaded if the platform supports it, and that&rsquo;s it. The
                point of the benchmark is the experience a real team would have, not a
                custom-tuned configuration we built.
              </p>
            </Reveal>

            <div className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-[var(--color-line)] ring-line md:grid-cols-2 lg:grid-cols-3">
              {systems.map((s) => (
                <Reveal key={s.id} className="bg-[var(--color-ink-1)] p-5">
                  <div className="font-mono text-[13px] text-[var(--color-text)]">{s.label}</div>
                  <p className="mt-1.5 text-[12.5px] leading-[1.5] text-[var(--color-text-muted)]">{s.note}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* Commit-to-publish */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <div className="rounded-2xl border border-[var(--color-flame)]/25 bg-[var(--color-ink-1)]/80 p-10 sm:p-14">
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                  Commit to publish
                </p>
                <h2 className="mt-3 text-balance text-[28px] font-semibold tracking-[-0.025em] sm:text-[34px]">
                  Whatever the numbers say, we&rsquo;ll publish them.
                </h2>
                <p className="mt-4 max-w-3xl text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                  The full raw corpus, the rater scoring rubric, the per-string rater scores
                  (anonymised), and the aggregate tables will land as a single open data drop on
                  GitHub, with a long-form writeup on this page. If Clariti loses on a locale, the
                  number is here and the fix shows up in the next release. If a vendor outperforms
                  us on a specific corpus, that&rsquo;s information you deserve before paying for
                  the bundle.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  <a
                    href={`${site.github}/issues/new?title=%5Bbenchmark%5D+`}
                    className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)]"
                  >
                    Get notified when results land
                  </a>
                  <a
                    href={`${site.github}/issues/new?title=%5Bbenchmark%5D+`}
                    className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] hover:border-[var(--color-flame)]/40 hover:text-white"
                  >
                    Suggest a corpus or a system →
                  </a>
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
