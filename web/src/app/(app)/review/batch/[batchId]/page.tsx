"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Flag, MessageSquare, Pencil, X } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { KeyboardChip } from "@/components/app-shell";
import { QaScores } from "@/components/qa-scores";
import { StatusChip } from "@/components/status-chip";
import { api, getApiKey, type Key, type Translation } from "@/lib/api";
import { useKeyBindings } from "@/lib/keyboard";
import { cn } from "@/lib/utils";
import { useHelpDialog } from "@/app/(app)/_help/help-dialog";

/**
 * Screen-based review (docs/06-human-review-workflow.md "Screen-based
 * review"). All strings in a batch are shown together so reviewers can
 * judge consistency at a screen level. Keyboard shortcuts per docs/06:
 *
 *   A          approve current row → approved
 *   r          reject current row  → rejected
 *   f          flag current row    → needs_more_context
 *   e          enter edit mode on current row
 *   j / k      move cursor down / up
 *   Cmd+Enter  save edit
 *   Escape     cancel edit
 *   Shift+A    approve every visible row that's currently needs_review
 *   ?          help dialog (Phase 6 — global overlay, see `_help/help-dialog.tsx`)
 *
 * Updates are optimistic — TanStack Query patches the cache before the
 * server responds so the keyboard flow stays at typing speed.
 */
export default function BatchReviewPage() {
  const params = useParams<{ batchId: string }>();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  if (!getApiKey()) {
    return (
      <div className="p-12 text-sm text-app-text-secondary">
        Please <Link href="/sign-in" className="text-primary ml-1">sign in</Link>.
      </div>
    );
  }

  return <BatchReview batchId={params.batchId} projectId={projectId} />;
}

function BatchReview({ batchId, projectId }: { batchId: string; projectId: string | null }) {
  const qc = useQueryClient();
  const helpDialog = useHelpDialog();

  const batchQuery = useQuery({
    queryKey: ["review", "batch", batchId],
    queryFn: () => api.batches.get(batchId),
  });
  const translationsQuery = useQuery({
    queryKey: ["review", "batch-translations", batchId],
    queryFn: () => api.translations.listByBatch(batchId),
  });
  const keyIds = translationsQuery.data?.map((t) => t.key_id) ?? [];
  const keysQuery = useQuery({
    queryKey: ["review", "batch-keys", batchId, keyIds],
    queryFn: () => api.keys.listByIds(keyIds),
    enabled: keyIds.length > 0,
  });

  const rows = useMemo<ReviewRow[]>(() => {
    if (!translationsQuery.data || !keysQuery.data) return [];
    const keyMap = new Map(keysQuery.data.map((k) => [k.id, k]));
    return translationsQuery.data
      .map((t) => {
        const key = keyMap.get(t.key_id);
        if (!key) return null;
        return { translation: t, key };
      })
      .filter((r): r is ReviewRow => r !== null)
      .sort((a, b) => a.key.key.localeCompare(b.key.key));
  }, [translationsQuery.data, keysQuery.data]);

  const [activeIdx, setActiveIdx] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const updateMutation = useMutation({
    mutationFn: (vars: Parameters<typeof api.translations.update>[1] & { id: string }) =>
      api.translations.update(vars.id, vars),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["review", "batch-translations", batchId] });
      const prev = qc.getQueryData<Translation[]>(["review", "batch-translations", batchId]);
      qc.setQueryData<Translation[]>(["review", "batch-translations", batchId], (old) =>
        old?.map((t) => (t.id === vars.id ? { ...t, ...vars } : t)) ?? [],
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        qc.setQueryData(["review", "batch-translations", batchId], ctx.prev);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["review", "batch-translations", batchId] });
    },
  });

  function activeRow(): ReviewRow | undefined {
    return rows[activeIdx];
  }

  function moveCursor(delta: number) {
    setActiveIdx((i) => Math.max(0, Math.min(rows.length - 1, i + delta)));
    setEditingId(null);
  }

  function approve(row: ReviewRow) {
    updateMutation.mutate({
      id: row.translation.id,
      status: "approved",
      reviewer_action: "accept",
    });
  }

  function reject(row: ReviewRow) {
    updateMutation.mutate({
      id: row.translation.id,
      status: "rejected",
      reviewer_action: "reject",
    });
  }

  function flag(row: ReviewRow) {
    updateMutation.mutate({
      id: row.translation.id,
      status: "needs_more_context",
      reviewer_action: "needs_more_context",
    });
  }

  function startEdit(row: ReviewRow) {
    setEditingId(row.translation.id);
    setDraft(row.translation.value ?? row.translation.mt_value ?? "");
  }

  function saveEdit(row: ReviewRow) {
    if (draft.trim() === (row.translation.value ?? "").trim()) {
      setEditingId(null);
      return;
    }
    updateMutation.mutate({
      id: row.translation.id,
      value: draft,
      status: "approved",
      reviewer_action: "edit",
    });
    setEditingId(null);
  }

  function approveScreen() {
    for (const row of rows) {
      if (row.translation.status === "needs_review" || row.translation.status === "mt_proposed") {
        approve(row);
      }
    }
  }

  useKeyBindings([
    {
      key: "j",
      description: "Next row",
      handler: () => moveCursor(1),
    },
    {
      key: "k",
      description: "Previous row",
      handler: () => moveCursor(-1),
    },
    {
      key: "a",
      description: "Approve current row",
      handler: () => {
        const r = activeRow();
        if (r) approve(r);
      },
    },
    {
      key: "A",
      shift: true,
      description: "Approve all needs_review rows in this batch",
      handler: () => approveScreen(),
    },
    {
      key: "r",
      description: "Reject current row",
      handler: () => {
        const r = activeRow();
        if (r) reject(r);
      },
    },
    {
      key: "f",
      description: "Flag for more context",
      handler: () => {
        const r = activeRow();
        if (r) flag(r);
      },
    },
    {
      key: "e",
      description: "Edit current row",
      handler: () => {
        const r = activeRow();
        if (r) startEdit(r);
      },
    },
    {
      key: "Escape",
      description: "Cancel edit",
      whileTyping: true,
      handler: () => setEditingId(null),
    },
    {
      key: "Enter",
      meta: true,
      whileTyping: true,
      description: "Save edit",
      handler: () => {
        const r = activeRow();
        if (r && editingId === r.translation.id) saveEdit(r);
      },
    },
    {
      // The review surface registers `?` locally so the chord works even
      // before any global listener attaches (e.g. during the first render
      // after a navigation). The app-shell also registers it — first match
      // wins and either path opens the same singleton dialog.
      key: "?",
      shift: true,
      description: "Open keyboard shortcut help",
      handler: () => helpDialog.open(),
    },
  ]);

  const isLoading = batchQuery.isLoading || translationsQuery.isLoading || keysQuery.isLoading;
  if (isLoading) {
    return (
      <div className="p-6 flex flex-col gap-3 max-w-5xl">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
        <Skeleton className="h-12" />
      </div>
    );
  }

  if (!batchQuery.data) {
    return <div className="p-12 text-sm text-app-text-muted">Batch not found.</div>;
  }

  const batch = batchQuery.data;
  const queueLink = projectId ? `/review/${batch.locale}?project=${projectId}` : `/review/${batch.locale}`;

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 pb-3 max-w-5xl w-full">
        <div className="flex items-center gap-2 text-sm text-app-text-secondary mb-2">
          <Link href="/dashboard" className="hover:text-app-text">Dashboard</Link>
          <ChevronRight className="size-3.5" />
          <Link href={queueLink} className="hover:text-app-text font-mono">
            {batch.locale}
          </Link>
          <ChevronRight className="size-3.5" />
          <span className="text-app-text">{batch.component ?? "shared"} · {batch.screen ?? "—"}</span>
        </div>
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <h1 className="text-lg font-semibold tracking-tight">
            {batch.component ?? "shared"} <span className="text-app-text-secondary">/</span>{" "}
            {batch.screen ?? "—"}
          </h1>
          <ShortcutLegend />
        </div>
      </div>

      <div className="flex-1 min-h-0 px-6 pb-6 overflow-auto">
        <Card className="max-w-5xl">
          <CardContent className="p-0 divide-y divide-app-border">
            {rows.length === 0 ? (
              <div className="p-8 text-center text-sm text-app-text-muted">
                No translations in this batch.
              </div>
            ) : (
              rows.map((row, idx) => (
                <ReviewRowItem
                  key={row.translation.id}
                  row={row}
                  active={idx === activeIdx}
                  editing={editingId === row.translation.id}
                  draft={draft}
                  setDraft={setDraft}
                  onFocus={() => setActiveIdx(idx)}
                  onApprove={() => approve(row)}
                  onReject={() => reject(row)}
                  onFlag={() => flag(row)}
                  onStartEdit={() => startEdit(row)}
                  onSaveEdit={() => saveEdit(row)}
                  onCancelEdit={() => setEditingId(null)}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

type ReviewRow = { translation: Translation; key: Key };

function ReviewRowItem({
  row,
  active,
  editing,
  draft,
  setDraft,
  onFocus,
  onApprove,
  onReject,
  onFlag,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
}: {
  row: ReviewRow;
  active: boolean;
  editing: boolean;
  draft: string;
  setDraft: (v: string) => void;
  onFocus: () => void;
  onApprove: () => void;
  onReject: () => void;
  onFlag: () => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
}) {
  const { translation: t, key } = row;
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (active && containerRef.current) {
      containerRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [active]);

  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(draft.length, draft.length);
    }
  }, [editing, draft.length]);

  // DESIGN.md "Review table": 2px left border in the status color for
  // needs_review / approved; 8% tinted background for rejected.
  const borderClass = (() => {
    switch (t.status) {
      case "needs_review":
        return "border-l-status-needs-review";
      case "mt_proposed":
        return "border-l-status-draft";
      case "approved":
      case "published":
        return "border-l-status-approved";
      case "rejected":
        return "border-l-status-rejected";
      case "needs_more_context":
        return "border-l-status-more-context";
      default:
        return "border-l-app-border";
    }
  })();
  const bgClass =
    t.status === "rejected"
      ? "bg-status-rejected/[0.06]"
      : active
        ? "bg-app-elevated/40"
        : undefined;

  return (
    <div
      ref={containerRef}
      onClick={onFocus}
      className={cn(
        "border-l-2 transition-colors",
        borderClass,
        bgClass,
        "p-4 flex flex-col gap-2",
      )}
      role="row"
      aria-selected={active}
    >
      <div className="flex items-baseline gap-3 flex-wrap">
        <code className="font-mono text-xs text-app-text-secondary">{key.key}</code>
        <StatusChip status={t.status} />
        {(t.qa_naturalness ?? t.qa_consistency ?? t.qa_accuracy) !== null &&
          (t.qa_naturalness ?? t.qa_consistency ?? t.qa_accuracy) !== undefined ? (
          <QaScores
            naturalness={t.qa_naturalness}
            consistency={t.qa_consistency}
            accuracy={t.qa_accuracy}
            backTranslationSimilarity={t.back_translation_similarity}
          />
        ) : null}
        {t.qa_issue ? (
          <Tooltip>
            <TooltipTrigger className="text-xs text-status-needs-review cursor-help">
              QA note
            </TooltipTrigger>
            <TooltipContent className="max-w-sm text-xs">{t.qa_issue}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <div className="text-[11px] uppercase tracking-wider text-app-text-muted">Source</div>
          <div className="text-sm leading-relaxed">{key.source_text}</div>
        </div>
        <div className="flex flex-col gap-1">
          <div className="text-[11px] uppercase tracking-wider text-app-text-muted">
            {t.locale}
          </div>
          {editing ? (
            <Textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="min-h-[80px] text-sm bg-app-input border-app-border-focus font-sans"
              spellCheck={false}
            />
          ) : (
            <div className="text-sm leading-relaxed">
              {t.value ?? t.mt_value ?? <span className="text-app-text-muted">(no translation)</span>}
            </div>
          )}
        </div>
      </div>

      {active ? (
        <div className="flex items-center gap-2 pt-1 flex-wrap">
          {editing ? (
            <>
              <Button size="sm" onClick={onSaveEdit}>
                Save <KeyboardChip>⌘↵</KeyboardChip>
              </Button>
              <Button size="sm" variant="secondary" onClick={onCancelEdit}>
                Cancel <KeyboardChip>esc</KeyboardChip>
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" onClick={onApprove} className="bg-status-approved/20 text-status-approved hover:bg-status-approved/30 border border-status-approved/40">
                <Check className="size-3.5 mr-1" />
                Approve <KeyboardChip>a</KeyboardChip>
              </Button>
              <Button size="sm" variant="secondary" onClick={onStartEdit}>
                <Pencil className="size-3.5 mr-1" />
                Edit <KeyboardChip>e</KeyboardChip>
              </Button>
              <Button size="sm" variant="secondary" onClick={onReject} className="text-status-rejected hover:text-status-rejected">
                <X className="size-3.5 mr-1" />
                Reject <KeyboardChip>r</KeyboardChip>
              </Button>
              <Button size="sm" variant="secondary" onClick={onFlag}>
                <Flag className="size-3.5 mr-1" />
                Flag <KeyboardChip>f</KeyboardChip>
              </Button>
              {t.reviewer_notes ? (
                <span className="text-xs text-app-text-muted inline-flex items-center gap-1">
                  <MessageSquare className="size-3.5" />
                  {t.reviewer_notes}
                </span>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ShortcutLegend() {
  return (
    <div className="hidden md:flex items-center gap-3 text-xs text-app-text-secondary">
      <span>
        <KeyboardChip>j</KeyboardChip>
        <KeyboardChip>k</KeyboardChip> navigate
      </span>
      <span>
        <KeyboardChip>a</KeyboardChip> approve
      </span>
      <span>
        <KeyboardChip>e</KeyboardChip> edit
      </span>
      <span>
        <KeyboardChip>r</KeyboardChip> reject
      </span>
      <span>
        <KeyboardChip>f</KeyboardChip> flag
      </span>
      <span>
        <KeyboardChip>⇧A</KeyboardChip> approve all
      </span>
    </div>
  );
}
