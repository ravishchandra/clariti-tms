import { cn } from "@/lib/cn";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 select-none", className)}>
      <svg
        width="22"
        height="22"
        viewBox="0 0 32 32"
        fill="none"
        aria-hidden
        className="text-[var(--color-flame)]"
      >
        <rect
          x="2.5"
          y="2.5"
          width="27"
          height="27"
          rx="6"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M9 11h10M9 16h14M9 21h7"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
        <circle cx="24" cy="21" r="1.5" fill="currentColor" />
      </svg>
      <span className="font-semibold tracking-tight text-[var(--color-text)]">
        Clariti<span className="text-[var(--color-text-muted)] font-normal">/tms</span>
      </span>
    </span>
  );
}
