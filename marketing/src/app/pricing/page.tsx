import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Reveal } from "@/components/Reveal";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: "Pricing — self-host free, commercial license available",
  description:
    "Clariti TMS is free to self-host under the AGPL-3.0. No per-seat fees. No per-string fees. A commercial license is available for organisations whose use is incompatible with the AGPL.",
  alternates: { canonical: "/pricing" },
  openGraph: {
    title: "Clariti TMS Pricing — self-host free, commercial license available",
    description:
      "Free self-host under AGPL-3.0. No seat fees, no string fees, no vendor cloud. Commercial license available.",
  },
};

const tiers = [
  {
    name: "Self-hosted",
    badge: "Open Source",
    price: "$0",
    sub: "per month, forever",
    cta: { label: "Try the playground →", href: "/playground", primary: true },
    body: "Run Clariti on your own infrastructure under the AGPL-3.0. No seat caps, no string caps, no feature gates.",
    perks: [
      "Unlimited users, projects, locales, strings",
      "All features — TM, glossary, back-translation QA, OTA, XLIFF",
      "Bring your own LLM provider — Claude, GPT, DeepL, Ollama",
      "GitHub PR-back and Contentful sync included",
      "Community support via GitHub Discussions",
      "AGPL-3.0 — your modifications stay yours unless you redistribute",
    ],
  },
  {
    name: "Managed (waitlist)",
    badge: "Coming Q4 2026",
    price: "Early access",
    sub: "no public pricing yet",
    cta: { label: "Join waitlist", href: site.github + "/discussions", primary: false },
    body: "Single-tenant managed deployment in your cloud account. We operate it — you own the data, the infra, and the LLM provider relationships.",
    perks: [
      "Single-tenant deployment in your AWS / GCP / Azure",
      "We handle upgrades, backups, monitoring, SLAs",
      "Your data never leaves your cloud account",
      "Production-grade observability and on-call",
      "Optional 24×7 support tier",
      "Pricing tied to compute, not seats",
    ],
    accent: true,
  },
  {
    name: "Commercial License",
    badge: "AGPL-incompatible use",
    price: "Talk to us",
    sub: "for hosted operators",
    cta: { label: "Contact maintainers", href: site.github, primary: false },
    body: "If you are building a hosted offering on top of Clariti and the AGPL is incompatible with how you want to ship, a commercial license is available.",
    perks: [
      "Use Clariti in a closed-source product",
      "Patches negotiated separately from the public roadmap",
      "Annual contract; CLA covers contributions back",
      "Optional priority bug-fix lane",
      "Optional architecture office hours",
      "Pricing scaled to revenue, not seats",
    ],
  },
];

export default function PricingPage() {
  return (
    <>
      <Nav />
      <main>
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-20 pb-12 lg:pt-28">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Pricing
              </p>
              <h1 className="mt-4 max-w-3xl text-balance text-[44px] font-bold leading-[1.05] tracking-[-0.04em] sm:text-[56px]">
                Free to run. Honest at scale.
              </h1>
              <p className="mt-5 max-w-2xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
                Clariti is open source. Self-hosting it costs zero — for one user or one thousand.
                We make money from organisations that need a commercial license or a managed
                deployment they do not have to run themselves.
              </p>
            </Reveal>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 pb-20">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {tiers.map((t, i) => (
                <Reveal key={t.name} delay={i * 80}>
                  <div
                    className={
                      "relative flex h-full flex-col rounded-xl border p-7 " +
                      (t.accent
                        ? "border-[var(--color-flame)]/35 bg-[var(--color-ink-1)]/90 shadow-flame"
                        : "border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/70")
                    }
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                        {t.badge}
                      </div>
                    </div>
                    <div className="mt-3 text-[22px] font-semibold tracking-tight">{t.name}</div>
                    <div className="mt-4 flex items-baseline gap-2">
                      <span className="text-[36px] font-bold tracking-[-0.03em] text-[var(--color-text)]">
                        {t.price}
                      </span>
                      <span className="text-[13px] text-[var(--color-text-muted)]">{t.sub}</span>
                    </div>
                    <p className="mt-5 text-[14px] leading-[1.6] text-[var(--color-text-soft)]">
                      {t.body}
                    </p>
                    <ul className="mt-6 space-y-2.5">
                      {t.perks.map((p) => (
                        <li
                          key={p}
                          className="flex items-start gap-2.5 text-[13.5px] text-[var(--color-text-soft)]"
                        >
                          <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-flame-soft)]" />
                          <span>{p}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-7 pt-6">
                      <a
                        href={t.cta.href}
                        className={
                          t.cta.primary
                            ? "inline-flex w-full items-center justify-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)]"
                            : "inline-flex w-full items-center justify-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] transition-all hover:border-[var(--color-flame)]/40 hover:text-white"
                        }
                      >
                        {t.cta.label}
                      </a>
                    </div>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-16">
            <Reveal>
              <h2 className="text-[28px] font-semibold tracking-[-0.03em]">
                Why pricing is structured this way
              </h2>
              <div className="prose mt-6 max-w-none space-y-5 text-[15px] leading-[1.7] text-[var(--color-text-soft)]">
                <p>
                  Hosted translation platforms have trained the market to expect{" "}
                  <span className="text-white">per-seat pricing</span> on top of{" "}
                  <span className="text-white">per-string pricing</span> on top of{" "}
                  <span className="text-white">per-feature gating</span>. The result is that adding
                  one more translator or one more locale becomes a procurement conversation, and
                  scaling translation quality with your product becomes a budget line item rather
                  than an engineering decision.
                </p>
                <p>
                  Clariti rejects that model. The software is free because it should be free —
                  every feature is in the open-source repo and you can run it without ever talking
                  to us. We charge only when we are doing something meaningful for you:
                  shipping a custom-licensed build, or operating a single-tenant managed
                  deployment in your cloud account.
                </p>
                <p>
                  If your scenario does not fit the three tiers above —{" "}
                  <Link href={site.github} className="text-[var(--color-flame-soft)] underline-offset-4 hover:underline">
                    open an issue on GitHub
                  </Link>
                  . We would rather have the conversation than guess.
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
