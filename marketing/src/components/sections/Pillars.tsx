import { Reveal } from "../Reveal";

export function Pillars() {
  return (
    <section id="features" className="relative">
      <div className="mx-auto max-w-7xl px-6 py-24">
        <Reveal>
          <div className="max-w-2xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
              Why teams switch
            </p>
            <h2 className="mt-4 text-balance text-[40px] font-[450] leading-[1.08] tracking-[-0.02em] sm:text-[52px]">
              Four things you cannot buy from a hosted TMS.
            </h2>
          </div>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-[var(--color-line)]/80 ring-line md:grid-cols-2">
          <Pillar
            n="01"
            title="Your data, your infrastructure"
            body="Every string, every translation, every screenshot, every cost log stays in your Postgres. AGPL-3.0 + Docker — runs on a laptop, a VPC, or an air-gapped box. Data residency is a feature, not a paid add-on."
            visual={<DataResidencyVisual />}
          />
          <Pillar
            n="02"
            title="Bring your own LLM"
            body="A Protocol-based provider interface ships Claude, GPT-4, DeepL, and Ollama out of the box. Swap providers per-locale, A/B them, or run a local model for regulated data. The prompt is yours."
            visual={<ProvidersVisual />}
          />
          <Pillar
            n="03"
            title="Screen-batch context, not isolated strings"
            body="Strings travel in their component. The pipeline sees the screen, the surrounding UI text, the glossary, and the 3 nearest TM matches before the LLM ever sees the source. Context fixes the 10–18% error rate everyone else absorbs as &ldquo;machine output.&rdquo;"
            visual={<ScreenBatchVisual />}
          />
          <Pillar
            n="04"
            title="Back-translation QA, by default"
            body="Every machine output is translated back into English and scored against the source on naturalness, consistency, and accuracy. Strings below the threshold route to a reviewer. You never ship a Czech sentence you cannot read."
            visual={<QaVisual />}
          />
        </div>
      </div>
    </section>
  );
}

function Pillar({
  n,
  title,
  body,
  visual,
}: {
  n: string;
  title: string;
  body: React.ReactNode;
  visual: React.ReactNode;
}) {
  return (
    <Reveal className="group relative flex flex-col gap-6 bg-[var(--color-ink-1)] p-7 sm:p-10">
      <div className="flex items-start justify-between">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
          / {n}
        </span>
      </div>
      <h3 className="text-balance text-[22px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)]">
        {title}
      </h3>
      <p className="text-pretty text-[14.5px] leading-[1.6] text-[var(--color-text-soft)]">
        {body}
      </p>
      <div className="mt-2 rounded-lg border border-[var(--color-line)]/80 bg-[var(--color-ink-2)]/80 p-4">
        {visual}
      </div>
    </Reveal>
  );
}

/* — visuals — */

function DataResidencyVisual() {
  return (
    <div className="grid grid-cols-2 gap-3 font-mono text-[11px]">
      <div className="rounded-md border border-[var(--color-line)] bg-[var(--color-ink-0)] p-3">
        <div className="text-[var(--color-text-muted)]">your infra</div>
        <div className="mt-1.5 flex items-center gap-1.5 text-[var(--color-mint)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)]" />
          postgres · pgvector
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-[var(--color-mint)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)]" />
          fastapi · review ui
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-[var(--color-mint)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)]" />
          screenshots · ota cdn
        </div>
      </div>
      <div className="rounded-md border border-dashed border-[var(--color-line-strong)] bg-[var(--color-ink-1)] p-3">
        <div className="text-[var(--color-text-muted)]">vendor cloud</div>
        <div className="mt-1.5 text-[var(--color-text-muted)]">— nothing —</div>
        <div className="mt-1 text-[var(--color-text-dim)]">no billing</div>
        <div className="mt-1 text-[var(--color-text-dim)]">no data egress</div>
      </div>
    </div>
  );
}

function ProvidersVisual() {
  const rows = [
    { p: "claude-sonnet-4", note: "default · UI" },
    { p: "gpt-4-turbo", note: "fallback" },
    { p: "openrouter/any", note: "one key · any model" },
    { p: "deepl/api", note: "fr, es, de plain" },
    { p: "ollama/llama3.1", note: "on-prem" },
  ];
  return (
    <div className="space-y-1.5 font-mono text-[12px]">
      {rows.map((r) => (
        <div
          key={r.p}
          className="flex items-center justify-between rounded border border-[var(--color-line)]/60 bg-[var(--color-ink-0)]/60 px-3 py-1.5"
        >
          <span className="text-[var(--color-text)]">{r.p}</span>
          <span className="text-[var(--color-text-muted)]">{r.note}</span>
        </div>
      ))}
    </div>
  );
}

function ScreenBatchVisual() {
  return (
    <div className="space-y-2 font-mono text-[11px]">
      <div className="flex items-center justify-between text-[var(--color-text-muted)]">
        <span>screen: CheckoutScreen.tsx</span>
        <span className="text-[var(--color-flame-soft)]">batch · 1 call</span>
      </div>
      <div className="rounded border border-[var(--color-line)] bg-[var(--color-ink-0)]/60 p-2.5">
        <Row k="title" v="Review your order" />
        <Row k="pay" v="Pay {amount}" />
        <Row k="eta" v="Arrives in 2–3 days" />
        <Row k="coupon" v="Coupon applied" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Tag color="iris">+ glossary (3)</Tag>
        <Tag color="mint">+ TM matches (3)</Tag>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5">
      <span className="w-12 shrink-0 text-[var(--color-text-muted)]">{k}</span>
      <span className="text-[var(--color-text)]">{v}</span>
    </div>
  );
}

function Tag({ children, color }: { children: React.ReactNode; color: "iris" | "mint" }) {
  const c = color === "iris" ? "var(--color-iris)" : "var(--color-mint)";
  return (
    <div
      className="rounded border px-2 py-1 text-center"
      style={{ color: c, borderColor: `${c}40`, background: `${c}10` }}
    >
      {children}
    </div>
  );
}

function QaVisual() {
  return (
    <div className="font-mono text-[11.5px]">
      <div className="flex items-center justify-between text-[var(--color-text-muted)]">
        <span>source → ja-JP → en-US</span>
        <span className="text-[var(--color-mint)]">passed</span>
      </div>
      <div className="mt-2 space-y-1.5">
        <div className="rounded border border-[var(--color-line)]/60 bg-[var(--color-ink-0)]/60 px-3 py-1.5">
          <div className="text-[var(--color-text-muted)]">source</div>
          <div className="text-[var(--color-text)]">Pay {`{amount}`}</div>
        </div>
        <div className="rounded border border-[var(--color-line)]/60 bg-[var(--color-ink-0)]/60 px-3 py-1.5">
          <div className="text-[var(--color-text-muted)]">back-translated</div>
          <div className="text-[var(--color-text)]">Pay {`{amount}`}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-2 text-center">
        <Score label="nat" v="4.8" />
        <Score label="cons" v="4.9" />
        <Score label="acc" v="4.9" />
        <Score label="back" v="0.96" />
      </div>
    </div>
  );
}

function Score({ label, v }: { label: string; v: string }) {
  return (
    <div className="rounded border border-[var(--color-line)]/60 bg-[var(--color-ink-0)]/60 px-2 py-1.5">
      <div className="text-[9.5px] uppercase tracking-wider text-[var(--color-text-muted)]">
        {label}
      </div>
      <div className="mt-0.5 text-[var(--color-mint)]">{v}</div>
    </div>
  );
}
