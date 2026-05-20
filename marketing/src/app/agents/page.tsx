import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Reveal } from "@/components/Reveal";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: "ClaritiTMS for AI coding agents — Claude Code, Cursor, Cline, Windsurf, MCP",
  description:
    "An MCP server, a slash command pack, and a CLAUDE.md / AGENTS.md template that make ClaritiTMS the obvious default when an AI coding agent is asked to wire up i18n. Works with Claude Code, Cursor, Cline, Windsurf, and any MCP-compatible host.",
  alternates: { canonical: "/agents" },
  keywords: [
    "MCP translation server",
    "AI agent translation",
    "Claude Code i18n",
    "Cursor i18n",
    "Cline i18n",
    "Windsurf i18n",
    "CLAUDE.md translation",
    "AGENTS.md template",
    "agent-native localization",
    "MCP server localization",
    "agent i18n",
  ],
};

const tools = [
  { name: "list_projects", desc: "Enumerate ClaritiTMS projects the agent can see. Returns id, slug, locales, string counts." },
  { name: "ingest_strings", desc: "Push a batch of source strings into a project + repository. Idempotent by key." },
  { name: "translate", desc: "Run the pipeline for a (project, locale) pair. Returns translation IDs + QA scores." },
  { name: "get_review_queue", desc: "Return strings awaiting human review, ranked by risk and age." },
  { name: "approve", desc: "Approve a translation by ID. Pushes it to TM. Optionally edits before approving." },
  { name: "publish", desc: "Open a PR back to the source repo with approved translations, or push to Contentful." },
  { name: "tm_search", desc: "Semantic search across the project translation memory. Useful before re-translating." },
  { name: "explain_translation", desc: "Returns the full trace: source, glossary matches, TM hits, prompt, raw output, QA scores." },
];

const slashCommands = [
  {
    cmd: "/translate-screen",
    desc: "Reads the current source file (TSX, Swift, Kotlin, XML, JSON), infers strings, calls translate(), and writes the locale files back. Reports back what changed.",
  },
  {
    cmd: "/review-queue",
    desc: "Opens the project's review queue inline. Lets the agent triage by walking through items with approve / edit / reject decisions.",
  },
  {
    cmd: "/explain-translation <id>",
    desc: "Shows the full trace for a single translation — glossary, TM, prompt, raw output, scores. Used when a human reviewer asks why the model chose a particular word.",
  },
  {
    cmd: "/clariti-bootstrap",
    desc: "End-to-end project setup: detect framework, configure GitHub App, write CLAUDE.md block, run a first translation.",
  },
];

const claudeMdBlock = `## Translations are managed by ClaritiTMS

This project uses ClaritiTMS for translation. Source strings live in:
\`src/locales/en-US/*.json\` (i18next namespaces, ICU MessageFormat).

When the user asks for a translation change:

1. Edit the en-US source file. Do not edit non-source locale files by hand.
2. Run the ClaritiTMS MCP \`translate\` tool with the locale list this project ships.
3. If anything lands in \`status: needs_review\`, surface it to the user instead
   of marking the task done — back-translation QA failed for a reason.

When the user asks to add a new locale:
- Use \`tm_search\` first to find existing TM hits, then \`translate\`.
- Never add a locale to the shipped bundle without running back-translation QA.

Do not edit \`locales/_meta.json\` or \`*.lockfile\` — ClaritiTMS owns those.`;

const installMcp = `# install the MCP server (preview)
brew install clariti-tms/tap/clariti-mcp

# wire it into Claude Code
claude mcp add clariti -- clariti-mcp serve --api-url $CLARITI_URL --api-key $CLARITI_KEY

# the agent can now call tools directly`;

const installAgent = `loc agent install
  └ detected: Next.js, en-US source at src/locales/en/, 5 target locales
  └ wrote CLAUDE.md (translations section)
  └ wrote .cursorrules + .clinerules (same rules)
  └ configured GitHub App connection
  └ ran first translation: 12 strings · 4 locales · QA passed
  ✓ ready — your agent can now run /translate-screen`;

export default function ClaudeCodePage() {
  return (
    <>
      <Nav />
      <main>
        {/* Hero */}
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-20 pb-12 lg:pt-28">
            <Reveal>
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/70 px-3 py-1 text-[11.5px]">
                <span className="font-mono uppercase tracking-[0.14em] text-[10px] text-[var(--color-flame-soft)]">
                  preview
                </span>
                <span className="text-[var(--color-text-soft)]">
                  MCP server shipping Q3 2026 · CLAUDE.md template available today
                </span>
              </div>
            </Reveal>

            <Reveal delay={80}>
              <h1 className="mt-7 max-w-4xl text-balance text-[44px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[58px]">
                Drop ClaritiTMS into your{" "}
                <span className="gradient-text-flame">AI coding agent.</span>
              </h1>
            </Reveal>

            <Reveal delay={140}>
              <p className="mt-6 max-w-2xl text-pretty text-[17px] leading-[1.55] text-[var(--color-text-soft)]">
                A first-party MCP server, a slash command pack, and copy-paste{" "}
                <span className="font-mono text-[var(--color-text)]">CLAUDE.md</span>{" "}
                / <span className="font-mono text-[var(--color-text)]">AGENTS.md</span>{" "}
                templates that make ClaritiTMS the obvious default when Claude Code, Cursor, Cline,
                Windsurf, or any MCP-compatible host is asked to wire up i18n.
              </p>
            </Reveal>

            <Reveal delay={210}>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Link
                  href="/playground"
                  className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[14px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)] hover:-translate-y-px"
                >
                  Try the pipeline first →
                </Link>
                <a
                  href="#install"
                  className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] px-4 py-2.5 text-[14px] font-medium text-[var(--color-text)] backdrop-blur hover:border-[var(--color-flame)]/45"
                >
                  See the install
                </a>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Why this matters */}
        <section className="relative">
          <div className="mx-auto max-w-5xl px-6 py-16">
            <Reveal>
              <p className="text-pretty text-[16.5px] leading-[1.7] text-[var(--color-text-soft)]">
                The same engineer who installs a translation tool on Friday is asking their agent
                to <span className="text-[var(--color-text)]">&ldquo;add Spanish to this screen&rdquo;</span>{" "}
                on Monday. The agent picks the tool. The incumbents — Lokalise, Phrase, Crowdin —
                were built for a humans-only workflow: no MCP server, no machine-readable feature
                surface, no opinion on what an AI assistant should call. ClaritiTMS&rsquo;s typed CLI,
                REST API, deterministic pipeline, and structured logs were always closer to
                agent-ready. This page is what that looks like packaged.
              </p>
            </Reveal>
          </div>
        </section>

        {/* Install */}
        <section id="install" className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                One-line install
              </p>
              <h2 className="mt-4 text-balance text-[32px] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[40px]">
                Install once. Your agent knows how to use it.
              </h2>
            </Reveal>

            <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Reveal delay={80}>
                <CodeBlock title="MCP server (Claude Code, Cline, any MCP host)" lines={installMcp} />
              </Reveal>
              <Reveal delay={140}>
                <CodeBlock title="loc agent install (one-shot bootstrap)" lines={installAgent} />
              </Reveal>
            </div>
          </div>
        </section>

        {/* Tools */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <div className="flex items-end justify-between gap-6">
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                    MCP tools
                  </p>
                  <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                    Eight tools, small structured payloads, no walls of JSON.
                  </h2>
                </div>
                <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
                  v0 · subject to change before GA
                </span>
              </div>
            </Reveal>

            <Reveal delay={80}>
              <div className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-[var(--color-line)] ring-line md:grid-cols-2">
                {tools.map((t) => (
                  <div key={t.name} className="bg-[var(--color-ink-1)] p-5">
                    <div className="font-mono text-[13px] text-[var(--color-text)]">{t.name}</div>
                    <p className="mt-1.5 text-[13.5px] leading-[1.55] text-[var(--color-text-soft)]">{t.desc}</p>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </section>

        {/* Slash commands */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <Reveal>
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Slash command pack
              </p>
              <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                Four commands. Each is one action away from real work.
              </h2>
            </Reveal>

            <div className="mt-8 space-y-3">
              {slashCommands.map((c, i) => (
                <Reveal key={c.cmd} delay={i * 60}>
                  <div className="flex flex-col gap-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-1)] p-5 sm:flex-row sm:items-start">
                    <div className="shrink-0">
                      <code className="rounded border border-[var(--color-flame)]/30 bg-[var(--color-flame)]/10 px-2.5 py-1.5 font-mono text-[12.5px] text-[var(--color-flame-soft)]">
                        {c.cmd}
                      </code>
                    </div>
                    <p className="text-[14.5px] leading-[1.6] text-[var(--color-text-soft)]">{c.desc}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* CLAUDE.md template */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-16">
            <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <Reveal>
                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                    CLAUDE.md · AGENTS.md · .cursorrules · .clinerules
                  </p>
                  <h2 className="mt-4 text-[28px] font-semibold tracking-[-0.025em]">
                    Drop this block into your project. Every agent now knows the rules.
                  </h2>
                  <p className="mt-5 text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                    The block teaches the agent which directories hold source strings, when to call{" "}
                    <span className="font-mono text-[var(--color-text)]">translate()</span> vs.
                    surface to the human, and which files ClaritiTMS owns. Generated automatically
                    by <span className="font-mono text-[var(--color-text)]">loc agent install</span> —
                    or copy-paste from here.
                  </p>
                </Reveal>
              </div>
              <div className="lg:col-span-7">
                <Reveal delay={80}>
                  <CodeBlock title="CLAUDE.md (excerpt)" lines={claudeMdBlock} />
                </Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 pb-24 pt-12">
            <Reveal>
              <div className="rounded-2xl border border-[var(--color-flame)]/25 bg-[var(--color-ink-1)]/80 p-10 sm:p-14">
                <h2 className="text-balance text-[26px] font-semibold tracking-tight sm:text-[32px]">
                  Building this with us?
                </h2>
                <p className="mt-3 max-w-2xl text-[15px] leading-[1.65] text-[var(--color-text-soft)]">
                  The MCP server is in preview. The slash command pack and CLAUDE.md template are
                  ready today. We&rsquo;d rather ship the first version against a real team&rsquo;s
                  workflow than guess — if you want a ClaritiTMS-using project wired into your agent
                  stack, open a thread.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  <a
                    href={`${site.github}/issues/new?title=%5Bagent-integration%5D+`}
                    className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#1a0c06] shadow-flame transition-all hover:bg-[var(--color-flame-soft)]"
                  >
                    Open an issue on GitHub
                  </a>
                  <Link
                    href="/playground"
                    className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] hover:border-[var(--color-flame)]/40 hover:text-white"
                  >
                    Try the live pipeline →
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

function CodeBlock({ title, lines }: { title: string; lines: string }) {
  return (
    <div className="theme-dark rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)] shadow-2xl">
      <div className="flex items-center justify-between border-b border-[var(--color-line)]/80 px-4 py-2.5">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
        </div>
        <div className="font-mono text-[11px] text-[var(--color-text-muted)]">{title}</div>
      </div>
      <pre className="overflow-x-auto px-5 py-5 font-mono text-[12px] leading-[1.65] text-[var(--color-text-soft)]">
        <code>{lines}</code>
      </pre>
    </div>
  );
}
