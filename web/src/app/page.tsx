import { redirect } from "next/navigation";

/**
 * Root: send straight to /dashboard. Sign-in lives at /sign-in and the
 * dashboard handles the "no API key" case by rendering an empty state
 * with a sign-in CTA.
 */
export default function RootPage() {
  redirect("/dashboard");
}
