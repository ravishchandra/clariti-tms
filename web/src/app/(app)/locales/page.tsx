import { redirect } from "next/navigation";

// Old top-level route kept as a redirect for in-app links pointing here
// (e.g. Settings → Project's FanoutNotice). The page body now lives at
// /settings/locales — see docs/14 IA v2.
export default function LocalesRedirect() {
  redirect("/settings/locales");
}
