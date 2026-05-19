"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

type Frame = {
  code: string;
  native: string;
  flag: string;
  rtl?: boolean;
  strings: {
    key: string;
    value: string;
    placeholder?: boolean;
  }[];
  qa: { naturalness: number; consistency: number; accuracy: number; back: number };
};

const frames: Frame[] = [
  {
    code: "en-US",
    native: "English (source)",
    flag: "EN",
    strings: [
      { key: "checkout.button.pay", value: "Pay {amount}" },
      { key: "checkout.title", value: "Review your order" },
      { key: "checkout.shipping.eta", value: "Arrives in 2–3 business days" },
      { key: "checkout.coupon.applied", value: "Coupon applied" },
    ],
    qa: { naturalness: 0, consistency: 0, accuracy: 0, back: 0 },
  },
  {
    code: "fr-FR",
    native: "Français",
    flag: "FR",
    strings: [
      { key: "checkout.button.pay", value: "Payer {amount}" },
      { key: "checkout.title", value: "Vérifiez votre commande" },
      { key: "checkout.shipping.eta", value: "Livraison sous 2 à 3 jours ouvrés" },
      { key: "checkout.coupon.applied", value: "Coupon appliqué" },
    ],
    qa: { naturalness: 4.8, consistency: 4.9, accuracy: 4.7, back: 0.96 },
  },
  {
    code: "ja-JP",
    native: "日本語",
    flag: "JP",
    strings: [
      { key: "checkout.button.pay", value: "{amount} を支払う" },
      { key: "checkout.title", value: "ご注文内容のご確認" },
      { key: "checkout.shipping.eta", value: "2〜3 営業日でお届けします" },
      { key: "checkout.coupon.applied", value: "クーポンを適用しました" },
    ],
    qa: { naturalness: 4.7, consistency: 4.8, accuracy: 4.9, back: 0.93 },
  },
  {
    code: "de-DE",
    native: "Deutsch",
    flag: "DE",
    strings: [
      { key: "checkout.button.pay", value: "{amount} bezahlen" },
      { key: "checkout.title", value: "Bestellung prüfen" },
      { key: "checkout.shipping.eta", value: "Lieferung in 2–3 Werktagen" },
      { key: "checkout.coupon.applied", value: "Gutschein angewendet" },
    ],
    qa: { naturalness: 4.6, consistency: 4.9, accuracy: 4.8, back: 0.95 },
  },
  {
    code: "ar-SA",
    native: "العربية",
    flag: "SA",
    rtl: true,
    strings: [
      { key: "checkout.button.pay", value: "ادفع {amount}" },
      { key: "checkout.title", value: "راجع طلبك" },
      { key: "checkout.shipping.eta", value: "يصل خلال 2–3 أيام عمل" },
      { key: "checkout.coupon.applied", value: "تم تطبيق القسيمة" },
    ],
    qa: { naturalness: 4.7, consistency: 4.8, accuracy: 4.8, back: 0.94 },
  },
];

export function LocaleCycler() {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const id = window.setInterval(() => setI((n) => (n + 1) % frames.length), 2800);
    return () => window.clearInterval(id);
  }, [paused]);

  const f = frames[i];
  const isSource = i === 0;

  return (
    <div
      className="theme-dark relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="absolute -inset-8 -z-10 rounded-3xl bg-gradient-to-br from-[var(--color-flame)]/12 via-transparent to-transparent blur-2xl" />

      <div className="rounded-xl border border-[var(--color-line-strong)] bg-[var(--color-ink-1)]/85 shadow-2xl backdrop-blur-md">
        {/* window chrome */}
        <div className="flex items-center justify-between border-b border-[var(--color-line)]/80 px-4 py-2.5">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-ink-4)]" />
          </div>
          <div className="font-mono text-[11px] text-[var(--color-text-muted)]">
            checkout.screen.tsx · v3
          </div>
          <div className="flex items-center gap-1 font-mono text-[11px] text-[var(--color-text-muted)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-mint)] pulse-dot" />
            <span>synced</span>
          </div>
        </div>

        {/* locale switcher row */}
        <div className="flex items-center gap-2 border-b border-[var(--color-line)]/60 bg-[var(--color-ink-2)]/40 px-4 py-2.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
            locale
          </span>
          <div className="flex items-center gap-1.5">
            {frames.map((fr, idx) => (
              <button
                key={fr.code}
                aria-label={`Switch to ${fr.code}`}
                onClick={() => setI(idx)}
                className={cn(
                  "rounded px-2 py-0.5 font-mono text-[10.5px] transition-all",
                  idx === i
                    ? "bg-[var(--color-flame)]/15 text-[var(--color-flame-soft)] ring-1 ring-[var(--color-flame)]/35"
                    : "text-[var(--color-text-muted)] hover:bg-[var(--color-ink-3)] hover:text-[var(--color-text-soft)]",
                )}
              >
                {fr.code}
              </button>
            ))}
          </div>
          <span className="ml-auto font-mono text-[10.5px] text-[var(--color-text-muted)]">
            {f.native}
          </span>
        </div>

        {/* strings table */}
        <div className="px-2 py-2" dir={f.rtl ? "rtl" : "ltr"}>
          {f.strings.map((s, idx) => (
            <div
              key={s.key}
              className="group flex items-start gap-3 rounded-md px-2.5 py-2.5 transition-colors hover:bg-[var(--color-ink-3)]/40"
            >
              <span
                className={cn(
                  "mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                  isSource ? "bg-[var(--color-text-muted)]" : "bg-[var(--color-mint)]",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div
                  dir="ltr"
                  className="truncate font-mono text-[11px] text-[var(--color-text-muted)]"
                >
                  {s.key}
                </div>
                <div
                  key={f.code + idx}
                  className="mt-0.5 animate-[fade_500ms_ease-out] text-[13.5px] leading-[1.45] text-[var(--color-text)]"
                >
                  {s.value}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* QA strip */}
        <div className="grid grid-cols-4 gap-px overflow-hidden rounded-b-xl border-t border-[var(--color-line)]/60 bg-[var(--color-line)]/60">
          <QaCell label="Naturalness" value={f.qa.naturalness} max={5} hidden={isSource} />
          <QaCell label="Consistency" value={f.qa.consistency} max={5} hidden={isSource} />
          <QaCell label="Accuracy" value={f.qa.accuracy} max={5} hidden={isSource} />
          <QaCell label="Back-trans" value={f.qa.back} max={1} hidden={isSource} unit="" />
        </div>
      </div>

      <style>{`@keyframes fade { from { opacity: 0; transform: translateY(2px) } to { opacity: 1; transform: none } }`}</style>
    </div>
  );
}

function QaCell({
  label,
  value,
  max,
  hidden,
  unit,
}: {
  label: string;
  value: number;
  max: number;
  hidden?: boolean;
  unit?: string;
}) {
  const ratio = value / max;
  const color =
    hidden || value === 0
      ? "var(--color-text-muted)"
      : ratio >= 0.8
        ? "var(--color-mint)"
        : ratio >= 0.6
          ? "var(--color-flame)"
          : "var(--color-rose)";
  return (
    <div className="bg-[var(--color-ink-1)] px-3 py-2.5">
      <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-[13px] tabular-nums" style={{ color }}>
        {hidden || value === 0 ? "—" : (unit === "" ? value.toFixed(2) : value.toFixed(1))}
      </div>
    </div>
  );
}
