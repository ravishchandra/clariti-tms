import { Reveal } from "../Reveal";
import { site } from "@/lib/site";

export function OpenSource() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-7xl px-6 py-24">
        <Reveal>
          <div className="relative overflow-hidden rounded-2xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/80">
            <div className="absolute -right-32 -top-32 h-[420px] w-[420px] rounded-full bg-[var(--color-flame)]/[0.08] blur-3xl" />
            <div className="absolute -bottom-32 -left-32 h-[420px] w-[420px] rounded-full bg-[var(--color-iris)]/[0.06] blur-3xl" />

            <div className="relative grid grid-cols-1 gap-10 p-10 lg:grid-cols-2 lg:p-14">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-flame-soft)]">
                  Open source · AGPL-3.0
                </p>
                <h2 className="mt-4 text-balance text-[30px] font-bold leading-[1.1] tracking-[-0.03em] sm:text-[36px]">
                  Free for teams that run it themselves. Commercial license for hosted operators.
                </h2>
                <p className="mt-5 text-pretty text-[17px] leading-[1.7] text-[var(--color-text-soft)]">
                  Self-host ClaritiTMS without a license fee — forever. The AGPL&rsquo;s
                  network-copyleft clause means hosted operators publish their modifications, which
                  protects the project and keeps the upgrade path honest. Need a setup that is
                  incompatible with the AGPL? A commercial license is available.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg bg-[var(--color-line)]/70 ring-line sm:grid-cols-2">
                <Bullet k="0 $" v="self-host fee" />
                <Bullet k="CLA" v="signed via bot on first PR" />
                <Bullet k="DCO" v="every commit signed-off" />
                <Bullet k="ruff + pytest" v="enforced in CI" />
              </div>
            </div>

            <div className="relative flex flex-wrap items-center gap-3 border-t border-[var(--color-line)]/70 px-10 py-5 lg:px-14">
              <a
                href={site.github}
                className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2 text-[13px] font-medium text-[var(--color-text)] transition-all hover:border-[var(--color-flame)]/40"
              >
                View source on GitHub
              </a>
              <a
                href={`${site.github}/blob/main/CONTRIBUTING.md`}
                className="text-[13px] text-[var(--color-text-soft)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
              >
                Contributing guide
              </a>
              <a
                href={`${site.github}/blob/main/LICENSE`}
                className="text-[13px] text-[var(--color-text-soft)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
              >
                Read the AGPL
              </a>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Bullet({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-[var(--color-ink-1)] px-5 py-5">
      <div className="font-mono text-[18px] font-medium tracking-tight text-[var(--color-flame-soft)]">
        {k}
      </div>
      <div className="mt-1.5 text-[12.5px] leading-snug text-[var(--color-text-soft)]">{v}</div>
    </div>
  );
}
