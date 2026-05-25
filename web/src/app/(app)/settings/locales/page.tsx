import { redirect } from "next/navigation";

// Locale configuration lives at the top-level /locales route today. Settings
// → Locales surfaces it under the unified Settings hub per docs/14 IA v2.
// Eventually the page body moves into this route; for now we redirect to
// keep one source of truth.
export default function LocalesSettingsRedirect() {
  redirect("/locales");
}
