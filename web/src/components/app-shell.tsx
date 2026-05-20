"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Database,
  FileSpreadsheet,
  FolderTree,
  Languages,
  LayoutPanelTop,
  Settings,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
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

const SECTION_LINKS = [
  { href: "/glossary", label: "Glossary", icon: FolderTree },
  { href: "/locales", label: "Locales", icon: Languages },
  { href: "/contexts", label: "Contexts", icon: LayoutPanelTop },
  { href: "/imports", label: "Imports", icon: Upload },
  { href: "/exports", label: "Exports", icon: FileSpreadsheet },
  { href: "/keys", label: "Keys", icon: Database },
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
  return (
    <aside className="w-[220px] shrink-0 border-r border-app-border bg-app-surface flex flex-col">
      <div className="px-4 py-4 flex items-center gap-2">
        <div className="size-6 rounded-md bg-primary/20 grid place-items-center text-primary text-sm font-semibold">
          C
        </div>
        <div className="text-sm font-semibold tracking-tight">ClaritiTMS</div>
      </div>

      <Separator />

      <div className="px-3 pt-3 pb-2 text-xs font-medium uppercase tracking-wider text-app-text-secondary">
        Locales
      </div>
      <LocaleList />

      <Separator className="my-2" />

      <nav className="px-2 pb-4 flex flex-col gap-0.5">
        {SECTION_LINKS.map((item) => (
          <SidebarLink key={item.href} {...item} />
        ))}
      </nav>
    </aside>
  );
}

/**
 * Locale list — currently a static placeholder until the dashboard wires up
 * the actual project's target_locales. Renders the same row shape the
 * dashboard will use so the design is stable across the hand-off.
 */
function LocaleList() {
  // Read the currently-selected project from localStorage (set on dashboard).
  // Falls back to listing all of the caller's orgs' first project's locales.
  const projectsQuery = useQuery({
    queryKey: ["sidebar", "locales"],
    queryFn: async () => {
      const orgs = await api.organizations.list();
      if (orgs.length === 0) return { projectName: "—", locales: [] as string[] };
      const projects = await api.projects.list(orgs[0].id);
      if (projects.length === 0) return { projectName: orgs[0].name, locales: [] as string[] };
      const project = projects[0];
      return { projectName: project.name, locales: project.target_locales };
    },
  });

  if (projectsQuery.isLoading) {
    return (
      <div className="px-3 flex flex-col gap-1">
        <Skeleton className="h-7" />
        <Skeleton className="h-7" />
        <Skeleton className="h-7" />
      </div>
    );
  }

  if (projectsQuery.isError || !projectsQuery.data) {
    return (
      <div className="px-3 py-2 text-xs text-app-text-muted">
        Sign in to load locales.
      </div>
    );
  }

  const { locales } = projectsQuery.data;
  if (locales.length === 0) {
    return (
      <div className="px-3 py-2 text-xs text-app-text-muted">No locales yet.</div>
    );
  }

  return (
    <ul className="px-2 flex flex-col gap-0.5">
      {locales.map((locale) => (
        <SidebarLocaleRow key={locale} locale={locale} />
      ))}
    </ul>
  );
}

function SidebarLocaleRow({ locale }: { locale: string }) {
  const pathname = usePathname();
  const href = `/review/${locale}`;
  const isActive = pathname?.startsWith(href);
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors",
          isActive
            ? "bg-app-elevated text-app-text border-l-2 border-primary -ml-[2px] pl-[10px]"
            : "text-app-text-secondary hover:bg-app-elevated/50 hover:text-app-text",
        )}
      >
        <span className="font-mono text-xs">{locale}</span>
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
        "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors",
        isActive
          ? "bg-app-elevated text-app-text"
          : "text-app-text-secondary hover:bg-app-elevated/50 hover:text-app-text",
      )}
    >
      <Icon className="size-4" />
      {label}
    </Link>
  );
}

/* ---------------------------------------------------------------------------
 * Top bar — page title + sign-in / sign-out chip. Kept thin (44px) per
 * the dense-data aesthetic.
 * ------------------------------------------------------------------------ */

function TopBar() {
  return (
    <header className="h-11 shrink-0 border-b border-app-border bg-app-surface/60 backdrop-blur-sm flex items-center justify-between px-4">
      <div className="text-xs text-app-text-secondary">
        Press <KeyboardChip>?</KeyboardChip> for shortcuts
      </div>
      <AuthChip />
    </header>
  );
}

export function KeyboardChip({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center px-1.5 py-0.5 rounded bg-app-elevated text-[11px] font-mono text-app-text-secondary border border-app-border">
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
      <Link href="/sign-in" className="text-xs text-primary hover:underline">
        Sign in
      </Link>
    );
  }
  const orgName = orgsQuery.data?.[0]?.name ?? "Unknown org";
  return (
    <Link href="/settings" className="text-xs text-app-text-secondary hover:text-app-text">
      {orgName}
    </Link>
  );
}
