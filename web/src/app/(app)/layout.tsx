import { AppShell } from "@/components/app-shell";

/**
 * Route group `(app)` — every page nested here renders inside the
 * sidebar + top-bar shell. The sign-in page lives outside the group
 * so it doesn't render the shell while the user is unauthenticated.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
