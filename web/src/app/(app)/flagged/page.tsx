"use client";

import { useQuery } from "@tanstack/react-query";
import { FlagIcon } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, getApiKey } from "@/lib/api";
import { useCurrentProject } from "@/lib/current-project";

/**
 * Flagged inbox (docs/14 §5 + W5). Surfaces every translation in
 * `needs_more_context` state for the current project. Before this page
 * existed, a reviewer pressing `f` set the flag in the DB but the PM had
 * to query SQL to find them — the flag pattern was end-to-end broken.
 *
 * Resolution: click into the key → reviewer pulls the right context →
 * status moves back to needs_review or approved.
 */
export default function FlaggedPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  if (!apiKey) {
    return (
      <div className="p-6 max-w-3xl text-sm text-text-soft">
        Sign in to see the flagged inbox.
      </div>
    );
  }
  return <FlaggedContent />;
}

function FlaggedContent() {
  const { current, isLoading } = useCurrentProject();

  if (isLoading) {
    return (
      <div className="p-6 max-w-5xl flex flex-col gap-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  if (!current) {
    return (
      <div className="p-6 max-w-3xl text-sm text-text-soft">
        No project selected — pick one from the sidebar.
      </div>
    );
  }

  return <FlaggedList projectId={current.project.id} />;
}

function FlaggedList({ projectId }: { projectId: string }) {
  const flaggedQuery = useQuery({
    queryKey: ["flagged", projectId],
    queryFn: () =>
      api.translations.listByProject(projectId, {
        status: "needs_more_context",
        pageSize: 200,
      }),
  });

  const items = flaggedQuery.data?.items ?? [];

  return (
    <div className="p-6 max-w-5xl flex flex-col gap-5">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="mono-eyebrow">Inbox</p>
          <h1 className="mt-1 text-[28px] font-[450] leading-tight tracking-[-0.02em] text-foreground flex items-center gap-2">
            <FlagIcon className="size-5 text-flame-soft" />
            Flagged
          </h1>
          <p className="text-sm text-text-soft max-w-prose">
            Translations a reviewer flagged as <code className="font-mono">needs_more_context</code>.
            Add the missing context (component description, screenshot,
            per-string note), then move the row back to needs_review.
          </p>
        </div>
      </header>

      <Card>
        <CardContent className="p-0">
          {flaggedQuery.isLoading ? (
            <div className="p-6 flex flex-col gap-3">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : items.length === 0 ? (
            <div className="p-10 text-center">
              <FlagIcon className="size-6 text-text-muted mx-auto mb-3" />
              <div className="text-sm font-medium text-foreground">
                Nothing flagged.
              </div>
              <div className="mt-1 text-[12px] text-text-muted">
                Reviewers press <kbd className="font-mono">f</kbd> on a string in the screen-review view to add a context note.
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">Locale</TableHead>
                  <TableHead className="w-[40%]">Reviewer note</TableHead>
                  <TableHead className="w-[20%]">Flagged at</TableHead>
                  <TableHead className="w-[120px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-mono text-[11.5px] text-text-soft">
                      {t.locale}
                    </TableCell>
                    <TableCell className="text-[13px]">
                      {t.reviewer_notes ?? (
                        <span className="text-text-muted italic">
                          (no note)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-text-muted">
                      {t.reviewed_at
                        ? new Date(t.reviewed_at).toISOString().slice(0, 16).replace("T", " ")
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link
                        href={`/keys/${t.key_id}`}
                        className={buttonVariants({ variant: "outline", size: "sm" })}
                      >
                        Resolve
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
