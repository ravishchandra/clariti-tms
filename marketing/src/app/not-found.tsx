import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";

export default function NotFound() {
  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-6 py-32 text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-flame-soft)]">
          404 · not_found
        </p>
        <h1 className="mt-4 text-balance text-[48px] font-bold leading-[1.05] tracking-[-0.04em]">
          Translation missing for this URL.
        </h1>
        <p className="mt-5 text-[16px] text-[var(--color-text-soft)]">
          The page you are looking for has either been moved, never existed, or is waiting on a
          reviewer.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-md bg-[var(--color-flame)] px-4 py-2.5 text-[13.5px] font-semibold text-[#ffffff] shadow-flame transition-all hover:bg-[var(--color-flame-soft)]"
          >
            Back to home
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-ink-2)] px-4 py-2.5 text-[13.5px] font-medium text-[var(--color-text)] hover:border-[var(--color-flame)]/40 hover:text-white"
          >
            See pricing
          </Link>
        </div>
      </main>
      <Footer />
    </>
  );
}
