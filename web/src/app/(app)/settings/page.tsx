/**
 * /settings — placeholder index page.
 *
 * The Settings IA has multiple tabs (General, Team, Billing, Data, Providers,
 * API keys, Integrations); only Providers ships today. The index page exists
 * so the sidebar's "Settings" link resolves rather than 404ing.
 */
import Link from "next/link";

export default function SettingsIndexPage() {
  return (
    <div className="rounded-md border border-app-border bg-app-surface p-6 text-sm text-app-text-secondary">
      <p className="mb-3">
        Most settings are still being built. The shipped tab is{" "}
        <Link href="/settings/providers" className="underline text-app-text">
          Providers
        </Link>
        .
      </p>
    </div>
  );
}
