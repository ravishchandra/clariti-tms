import { redirect } from "next/navigation";

/**
 * The export builder moved under Settings → Data (/settings/data/export) so the
 * round-trip tools live in one place instead of an orphaned top-level route.
 * This stub redirects old links and bookmarks. Server component — the redirect
 * happens before any client render.
 */
export default function ExportsRedirect() {
  redirect("/settings/data/export");
}
