"use client";

import { ArrowDownToLine, ArrowUpFromLine, FileSpreadsheet, FileText } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { getApiKey } from "@/lib/api";

/**
 * Settings → Data (docs/14 §9 tab 5). Hub for Excel + TMX import/export.
 *
 * Existing implementations live at /imports and /exports for now; this page
 * groups them visually so admins can find them. A full relocation (folding
 * the pages into /settings/data/imports and /settings/data/exports) is a
 * follow-up that requires moving the page bodies, not the routing intent.
 *
 * Recent jobs list per docs/14 §6.5 is deferred — needs a backend endpoint
 * that lists import_jobs by org with timestamps + status.
 */
export default function DataPage() {
  if (typeof window !== "undefined" && !getApiKey()) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">
        Sign in to use import / export.
      </div>
    );
  }
  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-4xl flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">
          Data round-trip
        </h2>
        <p className="text-[13px] text-text-soft max-w-prose">
          Bulk export to Excel for offline review or LSP hand-off, then import
          the edited workbook back. Both flows are dry-run first; nothing
          commits without your confirmation.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ActionCard
          href="/exports"
          icon={<ArrowDownToLine className="size-4 text-flame-soft" />}
          title="Export to Excel"
          body="Pick locales + status filter, build an .xlsx with locked schema headers. One row per (key, locale)."
        />
        <ActionCard
          href="/imports"
          icon={<ArrowUpFromLine className="size-4 text-flame-soft" />}
          title="Import from Excel"
          body="Upload an edited workbook. Dry-run shows every change before commit; 24-hour rollback window."
        />
        <ActionCard
          href="#"
          icon={<FileSpreadsheet className="size-4 text-text-muted" />}
          title="TMX export"
          body="Translation memory exchange format. CLI only for now (`loc export-tm`); UI follow-up."
          disabled
        />
        <ActionCard
          href="#"
          icon={<FileText className="size-4 text-text-muted" />}
          title="Recent jobs"
          body="List of recent imports/exports with rollback links. Follow-up — backend list endpoint pending."
          disabled
        />
      </div>
    </div>
  );
}

function ActionCard({
  href,
  icon,
  title,
  body,
  disabled,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  body: string;
  disabled?: boolean;
}) {
  const inner = (
    <Card
      className={`transition-all ${
        disabled
          ? "opacity-60"
          : "hover:border-flame/35 hover:-translate-y-px cursor-pointer"
      }`}
    >
      <CardContent className="p-5 flex flex-col gap-2.5">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="text-[14px] font-semibold tracking-tight text-foreground">
            {title}
          </h3>
        </div>
        <p className="text-[13px] leading-relaxed text-text-soft">{body}</p>
      </CardContent>
    </Card>
  );
  if (disabled) return inner;
  return <Link href={href}>{inner}</Link>;
}
