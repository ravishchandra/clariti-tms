import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "outline" | "secondary";

type EmptyStateAction =
  | { label: string; href: string; variant?: ButtonVariant }
  | { label: string; onClick: () => void; variant?: ButtonVariant };

/**
 * Canonical empty / error / gate state (admin-UI audit #16). Replaces the ~9
 * copy-pasted local `EmptyShell` / `Empty` / `EmptyState` / `QueryError`
 * components and several bare gate divs that drifted across 3 padding scales
 * and 2 colour-token namespaces.
 *
 * Two shapes:
 *   - `center` (default): a full-bleed centred hero — for page-level "no data"
 *     and outage states. Supports an icon, body, and a primary/Retry action.
 *   - `inline`: the lightweight left-aligned text gate — for "Sign in to …" and
 *     "No project selected." guards inside a settings tab.
 *
 * The error+Retry case is just `<EmptyState>` with an onClick action
 * (`variant="outline"`), so there's no separate error component.
 */
export function EmptyState({
  title,
  body,
  action,
  icon,
  variant = "center",
  className,
}: {
  title: string;
  body?: string;
  action?: EmptyStateAction;
  icon?: React.ReactNode;
  variant?: "center" | "inline";
  className?: string;
}) {
  const actionEl = !action ? null : "href" in action ? (
    <Link href={action.href} className={buttonVariants({ variant: action.variant })}>
      {action.label}
    </Link>
  ) : (
    <Button variant={action.variant} onClick={action.onClick}>
      {action.label}
    </Button>
  );

  if (variant === "inline") {
    return (
      <div className={cn("px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft", className)}>
        {title}
        {body ? <p className="mt-1 text-text-muted">{body}</p> : null}
        {actionEl ? <div className="mt-3">{actionEl}</div> : null}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-1 items-center justify-center p-12", className)}>
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        {icon ? <div className="text-text-muted">{icon}</div> : null}
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        {body ? <p className="text-sm text-text-soft">{body}</p> : null}
        {actionEl}
      </div>
    </div>
  );
}
