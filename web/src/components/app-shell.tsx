"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Database,
  FlagIcon,
  FolderTree,
  LayoutDashboardIcon,
  PlusIcon,
  Settings,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import logoMark from "@/app/logo.png";

import { ProjectSwitcher } from "@/components/project-switcher";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";
import { useKeyBindings } from "@/lib/keyboard";
import { HelpDialogProvider, useHelpDialogState } from "@/app/(app)/_help/help-dialog";

/**
 * Application shell — fixed-width sidebar (220px) + scrollable main area.
 * Matches docs/DESIGN.md "Sidebar" section: flat list, no nested expansion,
 * active row uses elevated background + accent-coloured left border (2px).
 *
 * The sidebar lists the *current project's* target locales as the primary
 * navigation. Sections (Glossary, Locales, Imports, etc.) sit below the
 * locale list under a Separator.
 */
type AppShellProps = {
  children: React.ReactNode;
};

// Sidebar v2 (audit docs/14 §7 + IA v2). Project-scoped section at top
// (Dashboard, locale list, project tools), top-level Glossary (daily
// reference), then Settings hub. Locales / Contexts / Imports / Exports
// previously lived as top-level peers — they're now folded into Settings.
const PROJECT_LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon },
] as const;

const PROJECT_FOOTER_LINKS = [
  { href: "/keys", label: "Keys", icon: Database },
  { href: "/flagged", label: "Flagged", icon: FlagIcon },
] as const;

const TOP_LEVEL_LINKS = [
  { href: "/glossary", label: "Glossary", icon: FolderTree },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppShell({ children }: AppShellProps) {
  // HelpDialogProvider mounts a singleton `<HelpDialog>` next to `children`
  // so any page descendant can open the overlay via `useHelpDialog()`.
  return (
    <HelpDialogProvider>
      <AppShellInner>{children}</AppShellInner>
    </HelpDialogProvider>
  );
}

function AppShellInner({ children }: AppShellProps) {
  const helpDialog = useHelpDialogState();

  // Global `?` shortcut — opens the help overlay from anywhere in the app
  // (dashboard / queue / settings). The review batch page also registers a
  // local `?` binding that opens the same singleton dialog; calling `open`
  // twice on the same keydown is idempotent (open→open is still open), so
  // the two listeners don't fight. Close is handled by the base-ui Dialog
  // (Esc / outside click / close button).
  useKeyBindings([
    {
      key: "?",
      shift: true,
      description: "Open keyboard shortcut help",
      handler: () => helpDialog.setOpen(true),
    },
  ]);

  return (
    <div className="flex min-h-screen w-full">
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col">
        <TopBar />
        <div className="flex-1 min-h-0 overflow-auto">{children}</div>
      </main>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Sidebar
 * ------------------------------------------------------------------------ */

function Sidebar() {
  // Sidebar — marketing's low-chrome nav signature (Nav.tsx + Pillars.tsx
  // mono labels). Sections: brand row → project switcher → project-scoped
  // (Dashboard + locale list + project footer links) → top-level (Glossary,
  // Settings). docs/14 IA v2.
  return (
    <aside className="w-[220px] shrink-0 border-r border-line bg-app-surface flex flex-col">
      <div className="px-4 h-12 flex items-center gap-2">
        <Image
          src={logoMark}
          alt="ClaritiTMS"
          width={24}
          height={24}
          className="rounded-md"
          priority
        />
        <div className="text-[13.5px] font-semibold tracking-tight text-foreground">
          ClaritiTMS
        </div>
      </div>

      <Separator />

      <div className="pt-3 pb-2">
        <ProjectSwitcher />
      </div>

      <nav className="px-2 pb-2 flex flex-col gap-0.5">
        {PROJECT_LINKS.map((item) => (
          <SidebarLink key={item.href} {...item} />
        ))}
      </nav>

      <div className="px-3 pt-3 pb-1 mono-eyebrow">Locales</div>
      <LocaleList />

      <nav className="px-2 pt-3 pb-3 flex flex-col gap-0.5">
        {PROJECT_FOOTER_LINKS.map((item) => (
          <SidebarLink key={item.href} {...item} />
        ))}
      </nav>

      <Separator className="my-1" />

      <nav className="px-2 py-3 flex flex-col gap-0.5">
        {TOP_LEVEL_LINKS.map((item) => (
          <SidebarLink key={item.href} {...item} />
        ))}
      </nav>
    </aside>
  );
}

/**
 * Locale list — reads `target_locales` off the current project (set by the
 * project switcher) and renders one row per locale linking to /review/{loc}.
 * Each row shows a needs-review count chip fetched from `/batches`. The
 * `+ Add locale` row links to Settings → Project (docs/14 §7).
 */
function LocaleList() {
  const { current, isLoading } = useCurrentProject();

  if (isLoading) {
    return (
      <div className="px-3 flex flex-col gap-1">
        <Skeleton className="h-7" />
        <Skeleton className="h-7" />
        <Skeleton className="h-7" />
      </div>
    );
  }

  if (!current) {
    return (
      <div className="px-3 py-2 text-xs text-app-text-muted">
        Sign in to load locales.
      </div>
    );
  }

  const locales = current.project.target_locales;

  return (
    <ul className="px-2 flex flex-col gap-0.5">
      {locales.map((locale) => (
        <SidebarLocaleRow
          key={locale}
          locale={locale}
          projectId={current.project.id}
        />
      ))}
      <li>
        <Link
          href="/settings/project"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-[13px] text-text-muted hover:bg-ink-2/60 hover:text-text-soft transition-colors"
        >
          <PlusIcon className="size-3.5" />
          <span className="text-[12px]">Add locale</span>
        </Link>
      </li>
    </ul>
  );
}

function SidebarLocaleRow({
  locale,
  projectId,
}: {
  locale: string;
  projectId: string;
}) {
  const pathname = usePathname();
  const href = `/review/${locale}`;
  const isActive = pathname?.startsWith(href);

  // Needs-review queue depth, surfaced per docs/06:39-44. One small request
  // per locale, cached by TanStack — N=3-5 locales in practice.
  const queueQuery = useQuery({
    queryKey: ["sidebar-queue", projectId, locale],
    queryFn: () =>
      api.batches.listByProject(projectId, { locale, status: "needs_review" }),
    staleTime: 30_000,
  });
  const count = queueQuery.data?.length ?? 0;

  return (
    <li>
      <Link
        href={href}
        className={cn(
          "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-[13px] transition-colors",
          isActive
            ? "bg-ink-2 text-foreground border-l-2 border-flame -ml-[2px] pl-[10px]"
            : "text-text-soft hover:bg-ink-2/60 hover:text-foreground",
        )}
      >
        <span className="font-mono text-[11.5px]">{locale}</span>
        {count > 0 ? (
          <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-flame/15 text-flame-soft text-[10px] font-mono font-medium">
            {count}
          </span>
        ) : null}
      </Link>
    </li>
  );
}

function SidebarLink({
  href,
  label,
  icon: Icon,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const pathname = usePathname();
  const isActive = pathname?.startsWith(href);
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors",
        isActive
          ? "bg-ink-2 text-foreground"
          : "text-text-soft hover:bg-ink-2/60 hover:text-foreground",
      )}
    >
      <Icon className="size-3.5" />
      {label}
    </Link>
  );
}

/* ---------------------------------------------------------------------------
 * Top bar — page title + sign-in / sign-out chip. Kept thin (44px) per
 * the dense-data aesthetic.
 * ------------------------------------------------------------------------ */

function TopBar() {
  // Top bar — matches marketing/Nav.tsx silhouette: low-chrome, blurred,
  // hairline border-b, mono accents on the metadata. Height bumped from
  // h-11 to h-12 so it lines up with the sidebar logo row exactly.
  return (
    <header className="h-12 shrink-0 border-b border-line/70 bg-app-surface/70 backdrop-blur-md flex items-center justify-between px-5">
      <div className="text-[12px] text-text-soft">
        Press <KeyboardChip>?</KeyboardChip>
        <span className="ml-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-text-muted">
          shortcuts
        </span>
      </div>
      <AuthChip />
    </header>
  );
}

export function KeyboardChip({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-ink-2 text-[10.5px] font-mono text-text-soft border border-line">
      {children}
    </kbd>
  );
}

function AuthChip() {
  const orgsQuery = useQuery({
    queryKey: ["top-bar", "auth"],
    queryFn: api.organizations.list,
    retry: false,
  });

  if (orgsQuery.isLoading) {
    return <Skeleton className="h-5 w-32" />;
  }
  if (orgsQuery.isError) {
    return (
      <Link
        href="/sign-in"
        className="inline-flex items-center gap-1.5 text-[12px] font-medium text-flame-soft hover:text-flame"
      >
        Sign in
        <span aria-hidden>→</span>
      </Link>
    );
  }
  const orgName = orgsQuery.data?.[0]?.name ?? "Unknown org";
  return (
    <Link
      href="/settings"
      className="inline-flex items-center gap-2 text-[12px] text-text-soft hover:text-foreground"
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-mint" aria-hidden />
      {orgName}
    </Link>
  );
}
