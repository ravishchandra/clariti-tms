import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { PlaygroundClient } from "@/components/PlaygroundClient";

export const metadata: Metadata = {
  title: "Playground — see the translation pipeline run live",
  description:
    "Paste UI strings, pick a target locale and provider, and watch the full Clariti pipeline run in your browser: context resolution, prompt assembly, LLM translation, and back-translation QA. No signup. No API keys.",
  alternates: { canonical: "/playground" },
  openGraph: {
    title: "Playground · Clariti TMS",
    description:
      "See the full translation pipeline — context, prompt, translation, and back-translation QA — run live in your browser.",
  },
};

export default function PlaygroundPage() {
  return (
    <>
      <Nav />
      <main>
        <section className="relative">
          <div className="absolute inset-0 grid-bg" aria-hidden />
          <div className="mx-auto max-w-7xl px-6 pt-16 pb-8 lg:pt-20">
            <div className="max-w-3xl">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                Live playground
              </p>
              <h1 className="mt-4 text-balance text-[40px] font-bold leading-[1.04] tracking-[-0.04em] sm:text-[52px]">
                See every stage of the pipeline,{" "}
                <span className="gradient-text-flame">in your browser.</span>
              </h1>
              <p className="mt-5 text-pretty text-[16.5px] leading-[1.55] text-[var(--color-text-soft)]">
                Pick a sample screen, a target locale, and a provider — then watch Clariti resolve
                context, assemble the prompt, run the translation, and score it with
                back-translation QA. The same five stages you get from{" "}
                <span className="font-mono text-[var(--color-text)]">loc translate</span>.
              </p>
            </div>
          </div>
        </section>

        <section className="relative">
          <div className="mx-auto max-w-7xl px-6 py-8 pb-24">
            <PlaygroundClient />
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
