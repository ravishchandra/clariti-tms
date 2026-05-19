import { Reveal } from "../Reveal";
import { cn } from "@/lib/cn";

type Cell = { v: "yes" | "no" | "partial" | "paid" | "notyet"; note?: string };

type Row = {
  label: string;
  hint?: string;
  cells: [Cell, Cell, Cell, Cell, Cell]; // Clariti, Lokalise, Phrase, Crowdin, Weblate
};

const cols = ["Clariti", "Lokalise", "Phrase", "Crowdin", "Weblate"] as const;

const rows: Row[] = [
  {
    label: "Self-hosted by default",
    hint: "Run on your own infra. No vendor cloud required.",
    cells: [{ v: "yes" }, { v: "no" }, { v: "no" }, { v: "partial", note: "Enterprise tier" }, { v: "yes" }],
  },
  {
    label: "Bring your own LLM",
    hint: "Choose provider per-locale: Claude, GPT, DeepL, Ollama.",
    cells: [{ v: "yes" }, { v: "partial", note: "AI add-on, fixed vendor" }, { v: "partial", note: "AI add-on, fixed vendor" }, { v: "partial" }, { v: "partial" }],
  },
  {
    label: "Screen-batch context",
    hint: "Entire UI screen sent as one prompt, not isolated strings.",
    cells: [{ v: "yes" }, { v: "no" }, { v: "no" }, { v: "no" }, { v: "no" }],
  },
  {
    label: "Back-translation QA",
    hint: "Every MT output back-translated and scored automatically.",
    cells: [{ v: "yes" }, { v: "no" }, { v: "partial", note: "Quality scoring only" }, { v: "no" }, { v: "no" }],
  },
  {
    label: "Translation memory (vector)",
    hint: "HNSW pgvector index, project-scoped, platform-ranked.",
    cells: [{ v: "yes" }, { v: "partial", note: "Fuzzy match" }, { v: "partial" }, { v: "partial" }, { v: "partial" }],
  },
  {
    label: "OTA delivery for mobile",
    hint: "Mobile apps fetch updated locales without an app-store release.",
    cells: [{ v: "yes" }, { v: "yes" }, { v: "partial" }, { v: "partial" }, { v: "no" }],
  },
  {
    label: "Native iOS .strings / .xcstrings",
    cells: [{ v: "yes" }, { v: "yes" }, { v: "yes" }, { v: "yes" }, { v: "partial" }],
  },
  {
    label: "Native Android strings.xml",
    cells: [{ v: "yes" }, { v: "yes" }, { v: "yes" }, { v: "yes" }, { v: "yes" }],
  },
  {
    label: "Professional reviewer marketplace",
    hint: "Hire vetted translators inside the platform. Clariti hands off via XLIFF / XLSX — not yet built-in.",
    cells: [
      { v: "notyet", note: "Not on the roadmap yet — hand off via XLIFF or XLSX to your LSP." },
      { v: "yes", note: "Integrated marketplace." },
      { v: "yes", note: "Memsource-heritage LSP marketplace." },
      { v: "yes", note: "Large integrated translator pool." },
      { v: "no" },
    ],
  },
  {
    label: "Open source",
    cells: [{ v: "yes", note: "AGPL-3.0" }, { v: "no" }, { v: "no" }, { v: "no" }, { v: "yes", note: "GPL-3.0" }],
  },
  {
    label: "Per-seat pricing",
    hint: "Lower is better.",
    cells: [{ v: "no", note: "Self-host = free" }, { v: "paid" }, { v: "paid" }, { v: "paid" }, { v: "no" }],
  },
  {
    label: "Data residency guaranteed",
    cells: [{ v: "yes" }, { v: "partial", note: "EU plan only" }, { v: "partial" }, { v: "partial" }, { v: "yes" }],
  },
];

export function Compare() {
  return (
    <section id="compare" className="relative">
      <div className="mx-auto max-w-7xl px-6 py-28">
        <Reveal>
          <div className="max-w-2xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
              Honest comparison
            </p>
            <h2 className="mt-4 text-balance text-[34px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[42px]">
              Where the bundled-TMS model breaks down.
            </h2>
            <p className="mt-5 text-pretty text-[15.5px] leading-[1.6] text-[var(--color-text-soft)]">
              The hosted platforms do a lot well — mobile SDKs, polished editors, marketplace
              integrations. They also charge per seat for things that should be commodity. Here is
              where Clariti is materially different.
            </p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div className="mt-12 overflow-x-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-1)]/70 backdrop-blur">
            <table className="w-full min-w-[760px] border-separate border-spacing-0 text-[13.5px]">
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 border-b border-[var(--color-line)] bg-[var(--color-ink-1)]/95 px-5 py-4 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--color-text-muted)] backdrop-blur">
                    Capability
                  </th>
                  {cols.map((c, idx) => (
                    <th
                      key={c}
                      className={cn(
                        "border-b border-[var(--color-line)] px-4 py-4 text-center text-[12px] font-semibold tracking-tight",
                        idx === 0
                          ? "bg-[var(--color-flame)]/[0.08] text-[var(--color-flame-soft)]"
                          : "text-[var(--color-text-soft)]",
                      )}
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.label} className="group">
                    <th
                      scope="row"
                      className="sticky left-0 z-10 border-b border-[var(--color-line)]/60 bg-[var(--color-ink-1)]/95 px-5 py-4 text-left align-top font-normal text-[var(--color-text)] backdrop-blur"
                    >
                      <div className="font-medium">{r.label}</div>
                      {r.hint && (
                        <div className="mt-0.5 text-[12px] text-[var(--color-text-muted)]">
                          {r.hint}
                        </div>
                      )}
                    </th>
                    {r.cells.map((c, j) => (
                      <td
                        key={j}
                        className={cn(
                          "border-b border-[var(--color-line)]/60 px-4 py-4 text-center align-middle",
                          j === 0 && "bg-[var(--color-flame)]/[0.04]",
                        )}
                      >
                        <Mark c={c} accent={j === 0} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>

        <Reveal delay={180}>
          <p className="mt-5 text-[12.5px] text-[var(--color-text-muted)]">
            Capabilities of named vendors are tracked from their public docs and pricing pages as
            of 2026-05; check vendor pages for current state. Comparison reflects out-of-the-box
            defaults, not custom enterprise contracts.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

function Mark({ c, accent }: { c: Cell; accent?: boolean }) {
  if (c.v === "yes") {
    return (
      <span
        title={c.note}
        className={cn(
          "inline-flex h-6 w-6 items-center justify-center rounded-full ring-1",
          accent
            ? "bg-[var(--color-flame)]/15 text-[var(--color-flame-soft)] ring-[var(--color-flame)]/35"
            : "bg-[var(--color-mint)]/12 text-[var(--color-mint)] ring-[var(--color-mint)]/30",
        )}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
          <path
            d="M2.5 6.5 5 9l4.5-6"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </span>
    );
  }
  if (c.v === "partial") {
    return (
      <span
        title={c.note}
        className="inline-flex items-center gap-1 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-2 py-1 font-mono text-[10.5px] uppercase tracking-wider text-[var(--color-text-muted)]"
      >
        partial
      </span>
    );
  }
  if (c.v === "paid") {
    return (
      <span
        title={c.note}
        className="inline-flex items-center gap-1 rounded-md border border-[var(--color-rose)]/30 bg-[var(--color-rose)]/8 px-2 py-1 font-mono text-[10.5px] uppercase tracking-wider text-[var(--color-rose)]"
      >
        per seat
      </span>
    );
  }
  if (c.v === "notyet") {
    return (
      <span
        title={c.note}
        className="inline-flex items-center gap-1 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-2 py-1 font-mono text-[10.5px] uppercase tracking-wider text-[var(--color-text-soft)]"
      >
        not yet
      </span>
    );
  }
  return (
    <span
      title={c.note}
      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[var(--color-text-muted)]"
    >
      —
    </span>
  );
}
