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
  // Sidebar — restyled to match marketing/'s low-chrome nav signature
  // (Nav.tsx + Pillars.tsx mono labels). The "C" mark now uses the flame
  // tint instead of the previous shadcn primary tone, and section labels
  // use the editorial mono-eyebrow treatment (uppercase, tracking 0.18em,
  // flame-soft colour) so the dashboard and marketing share the same
  // information-hierarchy language.
  return (
    <aside className="w-[220px] shrink-0 border-r border-line bg-app-surface flex flex-col">
      <div className="px-4 h-12 flex items-center gap-2">
        <div className="size-6 rounded-md bg-flame/12 grid place-items-center text-flame-soft text-sm font-semibold ring-1 ring-flame/25">
          C
        </div>
        <div className="text-[13.5px] font-semibold tracking-tight text-foreground">
          ClaritiTMS
        </div>
      </div>

      <Separator />

      <div className="px-3 pt-4 pb-2 mono-eyebrow">Locales</div>
      <LocaleList />

      <Separator className="my-3" />

      <div className="px-3 pb-2 mono-eyebrow">Workspace</div>
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
          "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-[13px] transition-colors",
          isActive
            ? "bg-ink-2 text-foreground border-l-2 border-flame -ml-[2px] pl-[10px]"
            : "text-text-soft hover:bg-ink-2/60 hover:text-foreground",
        )}
      >
        <span className="font-mono text-[11.5px]">{locale}</span>
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
