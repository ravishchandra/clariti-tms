import { Reveal } from "../Reveal";

const stages = [
  { n: "01", t: "Ingest", s: "Pull strings from GitHub / Contentful into the canonical store. Diff-aware — only new and changed keys move forward." },
  { n: "02", t: "Resolve context", s: "Attach screen, component, screenshots, placeholders, ICU shape, and length budget to every string." },
  { n: "03", t: "Inject glossary + TM", s: "Match brand terms (terminology lock) and the three nearest project-scoped TM examples via HNSW vector search." },
  { n: "04", t: "Translate (LLM)", s: "Send the whole screen as one batch to your chosen provider. Versioned prompt, deterministic seeds where supported." },
  { n: "05", t: "Back-translate QA", s: "Re-translate the output into English; score naturalness, consistency, and accuracy. Below threshold → review queue." },
  { n: "06", t: "Human review", s: "Keyboard-first UI. Reviewers approve, edit, reject, or request more context. Edits feed back into TM." },
  { n: "07", t: "Publish", s: "Open a PR against the source repo, push to Contentful, or serve via the OTA endpoint for mobile." },
];

export function Pipeline() {
  return (
    <section id="how-it-works" className="relative">
      <div className="mx-auto max-w-7xl px-6 py-28">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                The pipeline
              </p>
              <h2 className="mt-4 text-balance text-[34px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[42px]">
                Seven stages. Versioned. Auditable.
              </h2>
              <p className="mt-5 text-pretty text-[15.5px] leading-[1.6] text-[var(--color-text-soft)]">
                Each stage is a separate function with its own tests, its own cost log, and its
                own prompt version. The state machine is the source of truth — not a Notion doc.
              </p>
              <div className="mt-7 inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] px-3 py-2 font-mono text-[12px] text-[var(--color-text-soft)]">
                <span className="text-[var(--color-flame-soft)]">$</span>
                <span>
                  loc translate <span className="text-[var(--color-text-muted)]">--locale fr-FR</span>
                </span>
                <span className="caret" />
              </div>
            </Reveal>
          </div>

          <div className="lg:col-span-8">
            <Reveal delay={120}>
              <ol className="relative">
                <div
                  className="absolute left-[18px] top-2 bottom-2 w-px bg-gradient-to-b from-transparent via-[var(--color-line-strong)] to-transparent"
                  aria-hidden
                />
                {stages.map((st, i) => (
                  <li
                    key={st.n}
                    className="relative flex gap-5 pb-7 last:pb-0"
                  >
                    <div className="relative z-10 mt-0.5 flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] font-mono text-[11.5px] text-[var(--color-flame-soft)]">
                      {st.n}
                    </div>
                    <div className="min-w-0 flex-1 pt-1.5">
                      <div className="flex items-baseline justify-between gap-3">
                        <h3 className="text-[17px] font-semibold tracking-tight text-[var(--color-text)]">
                          {st.t}
                        </h3>
                        {i < stages.length - 1 && (
                          <svg
                            width="60"
                            height="10"
                            viewBox="0 0 60 10"
                            aria-hidden
                            className="hidden md:block text-[var(--color-flame)]/55"
                          >
                            <line
                              x1="0"
                              y1="5"
                              x2="60"
                              y2="5"
                              stroke="currentColor"
                              strokeWidth="1.25"
                              className="flow-dash"
                            />
                          </svg>
                        )}
                      </div>
                      <p className="mt-1 text-pretty text-[14.5px] leading-[1.55] text-[var(--color-text-soft)]">
                        {st.s}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}
