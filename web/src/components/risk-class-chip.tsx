import { cn } from "@/lib/utils";

/**
 * Risk-class pill — mirrors the status chip language but with its own
 * palette so reviewers can scan a Keys table without re-reading the
 * status legend. Values per docs/04-data-model.md `keys.risk_class`:
 *
 *   auto_publish  green   — MT auto-publishes, no human review
 *   standard      grey    — default, batch routes by QA score
 *   high_risk     red     — always needs review even on a clean QA pass
 *   human_only    purple  — never machine-translated
 */
export function RiskClassChip({ risk }: { risk: string | null | undefined }) {
  if (!risk) {
    return <span className="text-xs text-app-text-muted font-mono">—</span>;
  }
  const style = (() => {
    switch (risk) {
      case "auto_publish":
        return "bg-status-approved/15 text-status-approved";
      case "high_risk":
        return "bg-status-rejected/15 text-status-rejected";
      case "human_only":
        return "bg-status-bootstrapping/15 text-status-bootstrapping";
      default:
        return "bg-app-elevated/70 text-app-text-secondary";
    }
  })();
  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium font-mono",
        style,
      )}
    >
      {risk}
    </span>
  );
}
