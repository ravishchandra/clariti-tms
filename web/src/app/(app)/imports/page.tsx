import { redirect } from "next/navigation";

/**
 * The import wizard moved under Settings → Data (/settings/data/import) so the
 * round-trip tools live in one place instead of an orphaned top-level route.
 * This stub redirects old links and bookmarks. Server component — the redirect
 * happens before any client render.
 */
export default function ImportsRedirect() {
  redirect("/settings/data/import");
}
