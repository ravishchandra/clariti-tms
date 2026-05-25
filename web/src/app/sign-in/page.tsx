"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setApiKey } from "@/lib/api";

import logoMark from "@/app/logo.png";

/**
 * Sign-in screen — API-key entry, styled to echo the marketing hero
 * (grid-bg backdrop, mono-eyebrow + editorial headline + soft body
 * text). NextAuth / magic-link / SSO is the docs/09:159 plan; until
 * then we store the key in localStorage and send it as `X-API-Key`,
 * mirroring the CLI.
 */
export default function SignInPage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setSubmitting(true);
    setApiKey(value.trim());
    // Redirect after a microtask so the new localStorage value is picked up
    // by the dashboard's queries.
    setTimeout(() => router.replace("/dashboard"), 0);
  }

  return (
    <section className="relative isolate flex flex-1 items-center justify-center overflow-hidden px-6 py-16">
      <div className="absolute inset-0 grid-bg" aria-hidden />

      <div className="relative w-full max-w-md">
        <div className="flex flex-col items-center gap-3">
          <Image
            src={logoMark}
            alt="ClaritiTMS"
            width={56}
            height={56}
            className="rounded-lg"
            priority
          />
          <p className="mono-eyebrow">Sign in</p>
          <h1 className="text-balance text-center text-[34px] font-[450] leading-[1.08] tracking-[-0.02em] text-foreground">
            The translation system{" "}
            <span className="gradient-text-flame">you actually own.</span>
          </h1>
          <p className="text-pretty text-center text-[14px] leading-[1.6] text-text-soft max-w-sm">
            Paste an API key to enter the dashboard. The key stays in this
            browser only — same pattern the CLI uses.
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="mt-8 flex flex-col gap-4 rounded-xl border border-line-strong/80 bg-app-surface/80 p-6 backdrop-blur-sm shadow-flame/5"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="api-key" className="text-text-soft">
              API key
            </Label>
            <Input
              id="api-key"
              name="api-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="64-character hex from `loc api-key`"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              autoFocus
              className="font-mono text-[12.5px]"
            />
          </div>
          <Button
            type="submit"
            disabled={submitting || !value.trim()}
            className="w-full justify-center"
          >
            {submitting ? "Signing in…" : "Sign in"}
            <span aria-hidden className="ml-1 transition-transform group-hover/button:translate-x-0.5">
              →
            </span>
          </Button>
        </form>

        <div className="mt-6 flex flex-col gap-2 text-center text-[12px] text-text-muted">
          <p>
            No key yet?{" "}
            <code className="font-mono text-text-soft">loc api-key --name web</code>{" "}
            mints one locally.
          </p>
          <p>
            <Link
              href="https://github.com/anthropics/clariti-tms#readme"
              className="text-flame-soft hover:underline"
            >
              Read the docs
            </Link>{" "}
            ·{" "}
            <Link href="/sign-in" className="hover:text-text-soft">
              About this dashboard
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}
