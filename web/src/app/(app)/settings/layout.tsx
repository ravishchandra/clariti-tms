"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings/project", label: "Project" },
  { href: "/settings/repositories", label: "Repositories" },
  { href: "/settings/locales", label: "Locales" },
  { href: "/settings/data", label: "Data" },
  { href: "/settings/providers", label: "Providers" },
  { href: "/settings/api-keys", label: "API keys" },
] as const;

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col min-h-full">
      <div className="border-b border-line/70 bg-app-surface/40">
        <div className="px-6 pt-10 sm:px-8 sm:pt-12 pb-4 max-w-6xl">
          <p className="mono-eyebrow">Settings</p>
          <h1 className="mt-2 text-balance text-[30px] font-[450] leading-[1.08] tracking-[-0.018em] text-foreground sm:text-[34px]">
            Project &amp; admin
          </h1>
          <p className="mt-2 max-w-prose text-[14.5px] leading-[1.6] text-text-soft">
            Everything a project admin configures once: target locales, repositories,
            API keys, and the round-trip data tools.
          </p>
        </div>
        <nav className="px-3 sm:px-5 -mb-px flex items-center gap-1 overflow-x-auto">
          {TABS.map((tab) => {
            const active = pathname === tab.href || pathname?.startsWith(`${tab.href}/`);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "px-3 py-2.5 text-[13px] font-medium transition-colors border-b-2 -mb-px",
                  active
                    ? "text-foreground border-flame"
                    : "text-text-muted hover:text-text-soft border-transparent",
                )}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}
