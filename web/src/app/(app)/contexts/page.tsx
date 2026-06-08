import { redirect } from "next/navigation";

// Old top-level route kept as a redirect for any in-app links pointing here.
// The component-context editor now lives at /settings/contexts (see docs/14
// IA v2 — component_contexts is repo-scoped admin config, so it belongs under
// Settings). Previously this page was orphaned with no nav entry.
export default function ContextsRedirect() {
  redirect("/settings/contexts");
}
