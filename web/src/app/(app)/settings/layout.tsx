"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/**
 * Settings shell — horizontal tab nav at the top of every /settings/* page.
 *
 * "Providers" is the only tab with a shipped page today; the other entries
 * stay as visual placeholders so the IA reads correctly. Adding a page
 * later is just dropping a folder under `settings/<slug>/page.tsx` — the
 * layout already routes there.
 */
const TABS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/settings", label: "General" },
  { href: "/settings/team", label: "Team" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/data", label: "Data" },
  { href: "/settings/providers", label: "Providers" },
  { href: "/settings/api-keys", label: "API keys" },
  { href: "/settings/integrations", label: "Integrations" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-6 px-8 py-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-app-text-secondary mt-1">
          Workspace-wide configuration. Most changes apply on save.
        </p>
      </div>
      <nav
        aria-label="Settings sections"
        className="flex items-center gap-1 border-b border-app-border"
      >
        {TABS.map((tab) => {
          const isActive =
            tab.href === "/settings" ? pathname === "/settings" : pathname?.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
                isActive
                  ? "border-app-text text-app-text"
                  : "border-transparent text-app-text-secondary hover:text-app-text",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <div>{children}</div>
    </div>
  );
}
