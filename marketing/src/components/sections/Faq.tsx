import { Reveal } from "../Reveal";
import { faqs } from "@/lib/faq";

export function Faq() {
  return (
    <section id="faq" className="relative">
      <div className="mx-auto max-w-5xl px-6 py-28">
        <Reveal>
          <div className="max-w-2xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
              Frequently asked
            </p>
            <h2 className="mt-4 text-balance text-[40px] font-[450] leading-[1.08] tracking-[-0.02em] sm:text-[52px]">
              Questions worth answering well.
            </h2>
            <p className="mt-5 text-pretty text-[17px] leading-[1.7] text-[var(--color-text-soft)]">
              Each answer is written in full so search engines and AI answer engines can index it
              cleanly. Need something not covered here? Open an issue on GitHub.
            </p>
          </div>
        </Reveal>

        <div className="mt-12 divide-y divide-[var(--color-line)]/70 border-y border-[var(--color-line)]/70">
          {faqs.map((f, i) => (
            <Reveal key={f.q} delay={Math.min(i * 25, 200)}>
              <details className="group py-5">
                <summary className="flex cursor-pointer list-none items-baseline justify-between gap-6 text-[16px] font-medium tracking-tight text-[var(--color-text)] transition-colors hover:text-[var(--color-flame)]">
                  <span className="text-pretty">{f.q}</span>
                  <span className="font-mono text-[18px] text-[var(--color-flame-soft)] transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-4 max-w-3xl text-pretty text-[14.5px] leading-[1.7] text-[var(--color-text-soft)]">
                  {f.a}
                </p>
              </details>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export function FaqJsonLd() {
  const data = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
