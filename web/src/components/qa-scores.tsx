import { cn } from "@/lib/utils";

/**
 * QA score triplet — naturalness / consistency / accuracy, plus an
 * optional back-translation similarity number. Colors per docs/DESIGN.md
 * "QA score display": >= 4.0 green, 3.0–3.9 amber, < 3.0 red.
 */
function colorFor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-app-text-muted";
  if (score >= 4) return "text-qa-high";
  if (score >= 3) return "text-qa-mid";
  return "text-qa-low";
}

function similarityColor(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-app-text-muted";
  if (value >= 0.85) return "text-qa-high";
  if (value >= 0.7) return "text-qa-mid";
  return "text-qa-low";
}

export function QaScores({
  naturalness,
  consistency,
  accuracy,
  backTranslationSimilarity,
  className,
}: {
  naturalness?: number | null;
  consistency?: number | null;
  accuracy?: number | null;
  backTranslationSimilarity?: number | null;
  className?: string;
}) {
  const fmt = (s: number | null | undefined) => (s === null || s === undefined ? "—" : s.toFixed(1));
  return (
    <span className={cn("inline-flex items-center gap-2 font-mono text-xs", className)}>
      <span className={colorFor(naturalness)}>{fmt(naturalness)}</span>
      <span className="text-app-text-muted">·</span>
      <span className={colorFor(consistency)}>{fmt(consistency)}</span>
      <span className="text-app-text-muted">·</span>
      <span className={colorFor(accuracy)}>{fmt(accuracy)}</span>
      {backTranslationSimilarity !== undefined ? (
        <>
          <span className="text-app-text-muted ml-2">bt</span>
          <span className={similarityColor(backTranslationSimilarity)}>
            {backTranslationSimilarity === null ? "—" : backTranslationSimilarity.toFixed(2)}
          </span>
        </>
      ) : null}
    </span>
  );
}
