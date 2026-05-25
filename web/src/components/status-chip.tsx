import { cn } from "@/lib/utils";
import type { TranslationStatus } from "@/lib/api";

/**
 * Status chip — compact pill, 6px horizontal, 3px vertical, text-xs.
 * Filled background at ~20% opacity of the status color (DESIGN.md
 * "Status chips"). No icons inside — text only.
 */
type Variant = TranslationStatus | "mt_proposed" | "draft";

const STYLE_BY_STATUS: Record<Variant, string> = {
  // The token names come from globals.css — see docs/DESIGN.md "Color tokens".
  draft: "text-status-draft bg-status-draft/15",
  mt_proposed: "text-status-draft bg-status-draft/15",
  needs_review: "text-status-needs-review bg-status-needs-review/15",
  needs_more_context: "text-status-more-context bg-status-more-context/15",
  approved: "text-status-approved bg-status-approved/15",
  rejected: "text-status-rejected bg-status-rejected/15",
  published: "text-status-approved bg-status-approved/15",
};

const LABEL: Record<Variant, string> = {
  draft: "draft",
  mt_proposed: "mt proposed",
  needs_review: "needs review",
  needs_more_context: "needs context",
  approved: "approved",
  rejected: "rejected",
  published: "published",
};

export function StatusChip({
  status,
  count,
  className,
}: {
  status: Variant;
  count?: number;
  className?: string;
}) {
  // Mono-styled status chip — picks up the marketing site's editorial label
  // language (font-mono, 10.5px, uppercase, tracking-wide). The 15% tinted
  // background keeps the existing status colour coding so reviewers can
  // still scan a row at a glance.
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-md font-mono text-[10.5px] uppercase tracking-[0.06em] leading-none whitespace-nowrap",
        STYLE_BY_STATUS[status],
        className,
      )}
    >
      <span>{LABEL[status]}</span>
      {count !== undefined ? (
        <span className="text-text-muted">{count}</span>
      ) : null}
    </span>
  );
}
