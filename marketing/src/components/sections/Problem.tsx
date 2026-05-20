import { Reveal } from "../Reveal";

export function Problem() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-28">
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
        <div className="lg:col-span-5">
          <Reveal>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
              The state of localization
            </p>
            <h2 className="mt-4 text-balance text-[34px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[42px]">
              Translation became a SaaS subscription. It used to be a build artifact.
            </h2>
          </Reveal>
        </div>

        <div className="lg:col-span-7">
          <Reveal delay={120}>
            <p className="text-pretty text-[16.5px] leading-[1.6] text-[var(--color-text-soft)]">
              Every modern TMS bundles the same six things — a string database, an editor, a
              translation memory, context capture, CI plumbing, and a workflow state machine — and
              charges you per seat for the whole bundle. The actual moat sits in two of those
              layers: <span className="text-white">translation memory</span> and{" "}
              <span className="text-white">context-aware machine translation</span>. The rest is
              ergonomics.
            </p>
            <p className="mt-5 text-pretty text-[16.5px] leading-[1.6] text-[var(--color-text-soft)]">
              Meanwhile the model layer commoditised. Claude, GPT-4, DeepL and a strong glossary
              outperform any vendor&rsquo;s &ldquo;AI translation&rdquo; that wraps the same APIs —
              if you control the prompt, the memory, and the QA pipeline.
            </p>
            <p className="mt-5 text-pretty text-[16.5px] leading-[1.6] text-[var(--color-text-soft)]">
              ClaritiTMS is what you build when you stop paying for the wrapper.
            </p>
          </Reveal>

          <Reveal delay={220}>
            <div className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-[var(--color-line)]/80 ring-line sm:grid-cols-4">
              {[
                { v: "$140+", l: "Lokalise / mo, smallest plan" },
                { v: "$525+", l: "Phrase / mo, teams" },
                { v: "10–18%", l: "MT error rate without context" },
                { v: "0", l: "of your data ever leaves your infra" },
              ].map((s, i) => (
                <div
                  key={i}
                  className="bg-[var(--color-ink-1)] px-5 py-5"
                >
                  <div className="font-mono text-[20px] font-medium tracking-tight text-[var(--color-text)]">
                    {s.v}
                  </div>
                  <div className="mt-1.5 text-[12px] leading-snug text-[var(--color-text-muted)]">
                    {s.l}
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
