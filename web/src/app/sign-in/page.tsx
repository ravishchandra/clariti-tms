"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setApiKey } from "@/lib/api";

/**
 * Sign-in screen — API-key entry. NextAuth / magic-link / SSO is the
 * docs/09:159 plan but adds a backend dependency (mail provider) we
 * don't have set up yet. Storing the key in localStorage and exposing
 * it via `X-API-Key` is the same pattern the CLI uses.
 */
export default function SignInPage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setSubmitting(true);
    setApiKey(value.trim());
    // Redirect after a microtask so the new localStorage value is picked up
    // by the dashboard's queries.
    setTimeout(() => router.replace("/dashboard"), 0);
  }

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-lg">Sign in to Clariti TMS</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="api-key">API key</Label>
              <Input
                id="api-key"
                name="api-key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder="64-character hex key from `loc api-key`"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
                autoFocus
              />
              <p className="text-xs text-app-text-muted">
                Mint one locally with <code className="font-mono">loc api-key --name web</code>{" "}
                or via the REST API. Stored in your browser only, used as{" "}
                <code className="font-mono">X-API-Key</code> on every request.
              </p>
            </div>
            <Button type="submit" disabled={submitting || !value.trim()}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
