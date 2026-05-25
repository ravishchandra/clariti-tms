"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings/project", label: "Project" },
  { href: "/settings/repositories", label: "Repositories" },
  { href: "/settings/locales", label: "Locales" },
  { href: "/settings/data", label: "Data" },
  { href: "/settings/api-keys", label: "API keys" },
] as const;

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col min-h-full">
      <div className="border-b border-line/70 bg-app-surface/40">
        <div className="px-6 pt-6 pb-3">
          <p className="mono-eyebrow">Settings</p>
          <h1 className="mt-1 text-[28px] font-[450] leading-tight tracking-[-0.02em] text-foreground">
            Project &amp; admin
          </h1>
        </div>
        <nav className="px-3 -mb-px flex items-center gap-1 overflow-x-auto">
          {TABS.map((tab) => {
            const active = pathname === tab.href || pathname?.startsWith(`${tab.href}/`);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "px-3 py-2 text-[13px] font-medium transition-colors border-b-2",
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
