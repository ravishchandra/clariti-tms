"use client";

import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/cn";
import {
  availableLocales,
  availableProviders,
  buildFrame,
  renderPrompt,
  sampleSources,
  type SimulationFrame,
  type SourceString,
} from "@/lib/playground-data";

type Stage =
  | "idle"
  | "context"
  | "prompt"
  | "translate"
  | "qa"
  | "done";

const STAGE_ORDER: Stage[] = ["context", "prompt", "translate", "qa", "done"];

const STAGE_LABELS: Record<Exclude<Stage, "idle">, string> = {
  context: "Resolving context (glossary + TM)",
  prompt: "Assembling prompt",
  translate: "Calling provider",
  qa: "Back-translation QA",
  done: "Complete",
};

const STAGE_DELAYS_MS: Record<Exclude<Stage, "idle" | "done">, number> = {
  context: 280,
  prompt: 220,
  translate: 520,
  qa: 380,
};

export function PlaygroundClient() {
  const [sourceIdx, setSourceIdx] = useState(0);
  const [locale, setLocale] = useState("fr-FR");
  const [provider, setProvider] = useState(availableProviders[0].id);
  const [temperature, setTemperature] = useState(0);

  const [stage, setStage] = useState<Stage>("idle");
  const [frame, setFrame] = useState<SimulationFrame | null>(null);
  const [runId, setRunId] = useState(0);

  const sample = sampleSources[sourceIdx];

  // Build the prompt up-front so the prompt panel can show preview / final.
  const prompt = useMemo(
    () =>
      renderPrompt({
        sourceLabel: sample.label,
        sourceStrings: sample.strings,
        locale,
        provider,
        glossary: (frame?.glossary ?? buildFrame(sample.label, sample.strings, locale)?.glossary ?? []),
        tm: (frame?.tm ?? buildFrame(sample.label, sample.strings, locale)?.tm ?? []),
      }),
    [sample, locale, provider, frame],
  );

  // Run the simulator: walk through stages with realistic delays.
  useEffect(() => {
    if (stage === "idle" || stage === "done") return;
    const i = STAGE_ORDER.indexOf(stage);
    if (i < 0 || i >= STAGE_ORDER.length - 1) return;
    const next = STAGE_ORDER[i + 1];
    const delay = STAGE_DELAYS_MS[stage as keyof typeof STAGE_DELAYS_MS];
    const id = window.setTimeout(() => setStage(next), delay);
    return () => window.clearTimeout(id);
  }, [stage]);

  function run() {
    const built = buildFrame(sample.label, sample.strings, locale);
    if (!built) return;
    setFrame(built);
    setStage("context");
    setRunId((n) => n + 1);
  }

  function reset() {
    setFrame(null);
    setStage("idle");
  }

  const stageIndex = stage === "idle" ? -1 : STAGE_ORDER.indexOf(stage);
  const has = (s: Stage) => stageIndex >= STAGE_ORDER.indexOf(s);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* Controls */}
      <div className="lg:col-span-4">
        <div className="sticky top-20 rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] p-5">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Source
          </div>
          <div className="mt-2 grid grid-cols-1 gap-1.5">
            {sampleSources.map((s, i) => (
              <button
                key={s.label}
                onClick={() => {
                  setSourceIdx(i);
                  reset();
                }}
                className={cn(
                  "rounded-md border px-3 py-2 text-left text-[13px] transition-all",
                  i === sourceIdx
                    ? "border-[var(--color-flame)]/40 bg-[var(--color-flame)]/10 text-[var(--color-text)]"
                    : "border-[var(--color-line)] bg-[var(--color-ink-2)] text-[var(--color-text-soft)] hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>

          <div className="mt-5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Target locale
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {availableLocales.map((l) => (
              <button
                key={l.code}
                onClick={() => {
                  setLocale(l.code);
                  reset();
                }}
                className={cn(
                  "rounded border px-2.5 py-1 font-mono text-[11px] transition-all",
                  locale === l.code
                    ? "border-[var(--color-flame)]/40 bg-[var(--color-flame)]/10 text-[var(--color-flame-soft)]"
                    : "border-[var(--color-line)] bg-[var(--color-ink-2)] text-[var(--color-text-soft)] hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]",
                )}
              >
                {l.code}
              </button>
            ))}
          </div>

          <div className="mt-5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            Provider
          </div>
          <div className="mt-2 grid grid-cols-1 gap-1.5">
            {availableProviders.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setProvider(p.id);
                  reset();
                }}
                className={cn(
                  "flex items-baseline justify-between gap-2 rounded border px-2.5 py-1.5 text-left font-mono text-[11.5px] transition-all",
                  provider === p.id
                    ? "border-[var(--color-flame)]/40 bg-[var(--color-flame)]/10 text-[var(--color-text)]"
                    : "border-[var(--color-line)] bg-[var(--color-ink-2)] text-[var(--color-text-soft)] hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]",
                )}
              >
                <span>{p.label}</span>
                <span className="text-[10px] text-[var(--color-text-muted)]">{p.note}</span>
              </button>
            ))}
          </div>

          <div className="mt-5">
            <div className="flex items-center justify-between font-mono text-[10.5px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              <span>Temperature</span>
              <span className="text-[var(--color-text-soft)]">{temperature.toFixed(1)}</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="mt-2 w-full accent-[var(--color-flame)]"
            />
            <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
              0.0 = deterministic (UI strings default)
            </div>
          </div>

          <div className="mt-6 flex gap-2">
            <button
              onClick={run}
              className="flex-1 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#ffffff] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] disabled:opacity-50"
              disabled={stage !== "idle" && stage !== "done"}
            >
              {stage === "idle" || stage === "done" ? "Run pipeline →" : "Running…"}
            </button>
            {stage !== "idle" && (
              <button
                onClick={reset}
                className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-3 py-2.5 text-[13px] text-[var(--color-text-soft)] hover:text-[var(--color-text)]"
              >
                Reset
              </button>
            )}
          </div>

          <div className="mt-5 rounded-md border border-[var(--color-line)] bg-[var(--color-ink-2)] p-3">
            <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[var(--color-flame-soft)]">
              Preview · runs locally
            </div>
            <p className="mt-1.5 text-[11.5px] leading-[1.5] text-[var(--color-text-soft)]">
              This playground is a faithful client-side simulation of the real pipeline using
              hand-curated reference data. The shipped CLI (<code className="font-mono text-[var(--color-text)]">loc translate</code>)
              runs the same stages against your provider and your data. A live public instance is
              on the roadmap.
            </p>
          </div>
        </div>
      </div>

      {/* Output */}
      <div className="lg:col-span-8">
        <div className="theme-dark rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] shadow-2xl">
          {/* Source preview row */}
          <div className="border-b border-[var(--color-line)]/80 px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                Source · en-US
              </div>
              <div className="font-mono text-[11px] text-[var(--color-text-muted)]">
                {sample.strings.length} strings
              </div>
            </div>
            <div className="mt-3 space-y-1">
              {sample.strings.map((s) => (
                <div key={s.key} className="flex items-baseline gap-3 font-mono text-[12px]">
                  <span className="w-44 shrink-0 truncate text-[var(--color-text-muted)]">{s.key}</span>
                  <span className="text-[var(--color-text)]">{s.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Pipeline progress */}
          <PipelineProgress stage={stage} />

          {/* Stage panels */}
          <div className="divide-y divide-[var(--color-line)]/70">
            {/* Context */}
            <StagePanel title="Context resolution" subtitle="glossary + 3-NN TM matches" active={has("context")}>
              {has("context") && frame && (
                <div key={`ctx-${runId}`} className="grid grid-cols-1 gap-3 animate-[fade_400ms_ease-out] sm:grid-cols-2">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-iris)]">
                      Glossary ({frame.glossary.length})
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {frame.glossary.map((g) => (
                        <div
                          key={g.term}
                          className="rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-2.5 py-1.5"
                        >
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="font-mono text-[11.5px] text-[var(--color-text)]">{g.term}</span>
                            <span
                              className={cn(
                                "font-mono text-[9.5px] uppercase tracking-wider",
                                g.rule === "lock" && "text-[var(--color-rose)]",
                                g.rule === "placeholder" && "text-[var(--color-iris)]",
                                g.rule === "keep" && "text-[var(--color-text-muted)]",
                              )}
                            >
                              {g.rule}
                            </span>
                          </div>
                          <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">{g.note}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-mint)]">
                      TM matches ({frame.tm.length})
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {frame.tm.map((t) => (
                        <div
                          key={t.source}
                          className="rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-2.5 py-1.5"
                        >
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="font-mono text-[11.5px] text-[var(--color-text)]">&ldquo;{t.source}&rdquo;</span>
                            <span className="font-mono text-[10px] text-[var(--color-mint)]">sim {t.similarity.toFixed(2)}</span>
                          </div>
                          <div className="mt-0.5 font-mono text-[11px] text-[var(--color-text-soft)]">
                            → &ldquo;{t.target}&rdquo;
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </StagePanel>

            {/* Prompt */}
            <StagePanel title="Prompt assembly" subtitle="versioned · clariti.translate_v3" active={has("prompt")}>
              {has("prompt") && (
                <pre
                  key={`p-${runId}`}
                  className="overflow-x-auto rounded-md border border-[var(--color-line)] bg-[var(--color-ink-2)] p-4 font-mono text-[11px] leading-[1.6] text-[var(--color-text-soft)] animate-[fade_400ms_ease-out]"
                >
                  <code>{prompt}</code>
                </pre>
              )}
            </StagePanel>

            {/* Translate */}
            <StagePanel title={`Provider · ${provider}`} subtitle={`temperature ${temperature.toFixed(1)} · batch of ${sample.strings.length}`} active={has("translate")}>
              {has("translate") && frame && (
                <div
                  key={`t-${runId}`}
                  dir={frame.rtl ? "rtl" : "ltr"}
                  className="space-y-1.5 animate-[fade_400ms_ease-out]"
                >
                  {frame.translations.map((s) => (
                    <div
                      key={s.key}
                      className="flex items-start gap-3 rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-3 py-2"
                    >
                      <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-mint)]" />
                      <div className="min-w-0 flex-1">
                        <div dir="ltr" className="font-mono text-[10.5px] text-[var(--color-text-muted)]">
                          {s.key}
                        </div>
                        <div className="mt-0.5 text-[13px] text-[var(--color-text)]">{s.value}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </StagePanel>

            {/* QA */}
            <StagePanel title="Back-translation QA" subtitle={`${frame?.locale ?? ""} → en-US round-trip + 3-axis score`} active={has("qa")}>
              {has("qa") && frame && (
                <div key={`qa-${runId}`} className="grid grid-cols-1 gap-4 animate-[fade_400ms_ease-out] sm:grid-cols-5">
                  <div className="sm:col-span-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                      Back-translated → en-US
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {sample.strings.map((s, i) => {
                        const bt = frame.backTranslations[i]?.value ?? "—";
                        const match = bt.toLowerCase() === s.value.toLowerCase();
                        return (
                          <div
                            key={s.key}
                            className="rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-3 py-2"
                          >
                            <div className="font-mono text-[10.5px] text-[var(--color-text-muted)]">{s.key}</div>
                            <div className="mt-0.5 text-[12.5px] text-[var(--color-text-soft)]">
                              source: <span className="text-[var(--color-text)]">{s.value}</span>
                            </div>
                            <div className="mt-0.5 text-[12.5px]">
                              <span className="text-[var(--color-text-muted)]">back: </span>
                              <span className={match ? "text-[var(--color-mint)]" : "text-[var(--color-text)]"}>{bt}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="sm:col-span-2">
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                      Scores
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <Score label="Naturalness" v={frame.qa.naturalness.toFixed(1)} good={frame.qa.naturalness >= 4.0} />
                      <Score label="Consistency" v={frame.qa.consistency.toFixed(1)} good={frame.qa.consistency >= 4.0} />
                      <Score label="Accuracy" v={frame.qa.accuracy.toFixed(1)} good={frame.qa.accuracy >= 4.0} />
                      <Score label="Back-sim" v={frame.qa.back.toFixed(2)} good={frame.qa.back >= 0.85} />
                    </div>
                    <div
                      className={cn(
                        "mt-3 rounded-md border px-3 py-2 text-center text-[12.5px] font-medium",
                        frame.qa.passed
                          ? "border-[var(--color-mint)]/40 bg-[var(--color-mint)]/10 text-[var(--color-mint)]"
                          : "border-[var(--color-rose)]/40 bg-[var(--color-rose)]/10 text-[var(--color-rose)]",
                      )}
                    >
                      {frame.qa.passed ? "PASS · ready to publish" : "FAIL · routed to reviewer"}
                    </div>
                  </div>
                </div>
              )}
            </StagePanel>
          </div>
        </div>

        <style>{`@keyframes fade { from { opacity: 0; transform: translateY(4px) } to { opacity: 1; transform: none } }`}</style>
      </div>
    </div>
  );
}

function PipelineProgress({ stage }: { stage: Stage }) {
  const order = STAGE_ORDER.filter((s) => s !== "done");
  return (
    <div className="flex items-stretch border-b border-[var(--color-line)]/70 bg-[var(--color-ink-2)]/40">
      {order.map((s, i) => {
        const sIdx = STAGE_ORDER.indexOf(s);
        const cur = STAGE_ORDER.indexOf(stage);
        const state = stage === "idle" ? "idle" : sIdx < cur ? "done" : sIdx === cur ? "active" : "pending";
        return (
          <div
            key={s}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 px-3 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.12em] transition-colors",
              i > 0 && "border-l border-[var(--color-line)]/70",
              state === "done" && "text-[var(--color-mint)]",
              state === "active" && "text-[var(--color-flame-soft)]",
              state === "pending" && "text-[var(--color-text-muted)]",
              state === "idle" && "text-[var(--color-text-muted)]",
            )}
          >
            <span
              className={cn(
                "inline-block h-1.5 w-1.5 rounded-full",
                state === "done" && "bg-[var(--color-mint)]",
                state === "active" && "bg-[var(--color-flame)] pulse-dot",
                (state === "pending" || state === "idle") && "bg-[var(--color-text-muted)]/50",
              )}
            />
            <span className="hidden sm:inline">{STAGE_LABELS[s as Exclude<Stage, "idle">]}</span>
            <span className="sm:hidden">{i + 1}</span>
          </div>
        );
      })}
    </div>
  );
}

function StagePanel({
  title,
  subtitle,
  active,
  children,
}: {
  title: string;
  subtitle: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <details
      open={active}
      className={cn(
        "group transition-opacity",
        active ? "opacity-100" : "pointer-events-none opacity-40",
      )}
    >
      <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3 px-5 py-3.5 hover:bg-[var(--color-ink-2)]/50">
        <div className="flex items-baseline gap-2">
          <span className="text-[13.5px] font-semibold tracking-tight text-[var(--color-text)]">{title}</span>
          <span className="font-mono text-[10.5px] text-[var(--color-text-muted)]">{subtitle}</span>
        </div>
        <span className="font-mono text-[14px] text-[var(--color-text-muted)] transition-transform group-open:rotate-90">›</span>
      </summary>
      <div className="px-5 pb-5">{children}</div>
    </details>
  );
}

function Score({ label, v, good }: { label: string; v: string; good: boolean }) {
  return (
    <div className="rounded border border-[var(--color-line)] bg-[var(--color-ink-2)] px-3 py-2 text-center">
      <div className="font-mono text-[9.5px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div
        className={cn(
          "mt-0.5 font-mono text-[14px] tabular-nums",
          good ? "text-[var(--color-mint)]" : "text-[var(--color-rose)]",
        )}
      >
        {v}
      </div>
    </div>
  );
}

interface ExtendedSourceString extends SourceString {}
export type { ExtendedSourceString };
