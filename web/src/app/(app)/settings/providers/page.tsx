"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  GripVerticalIcon,
  PlusIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, getApiKey, type AppSettings, type AppSettingsUpdate } from "@/lib/api";

/**
 * Settings → Providers — single form, single Save.
 *
 * Edits the singleton `app_settings` row that backs LLM provider
 * configuration. API keys are write-only (server returns booleans) and
 * empty submit on a key field clears that provider.
 *
 * Visual rhythm matches sibling Settings tabs (Project, Repositories, API
 * keys): each section is `<h2 text-sm font-semibold>` above a `<Card>` with
 * `p-5` padding. Tokens are marketing-aligned (`text-text-soft`,
 * `text-mint`, `text-status-rejected`); no raw Tailwind color primitives.
 */
const PROVIDERS = ["anthropic", "openai", "openrouter", "ollama", "deepl"] as const;

export default function ProvidersPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  if (!apiKey) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl text-sm text-text-soft">
        Sign in with an API key to edit provider settings.
      </div>
    );
  }
  return <ProvidersForm />;
}

function ProvidersForm() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["app-settings"],
    queryFn: api.appSettings.get,
    retry: false,
  });

  if (query.isLoading) return <FormSkeleton />;
  if (query.isError || !query.data) {
    return (
      <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl">
        <Card className="border-status-rejected/30 bg-status-rejected/5">
          <CardContent className="p-4 text-sm text-status-rejected">
            Couldn&apos;t load provider settings. The migration may not have run yet.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <ProvidersFormBody
      initial={query.data}
      onSaved={() => qc.invalidateQueries({ queryKey: ["app-settings"] })}
    />
  );
}

type SavedState =
  | { kind: "idle" }
  | { kind: "saved"; at: Date }
  | { kind: "error"; message: string };

function ProvidersFormBody({ initial, onSaved }: { initial: AppSettings; onSaved: () => void }) {
  // The form mirrors the server's two concerns: non-key fields
  // (round-tripped verbatim) and key fields (write-only, with a "set" /
  // "not set" pill driven by the boolean from the GET response).
  const [primaryProvider, setPrimaryProvider] = useState(initial.primary_provider);
  // Fallback chain edited as an ordered array of provider slugs. Internal
  // representation matches the wire format (server takes a JSON array);
  // the UI just stops asking the user to parse commas.
  const [fallbackChain, setFallbackChain] = useState<string[]>(initial.fallback_chain);
  const [openrouterModel, setOpenrouterModel] = useState(initial.openrouter_model);
  const [translateTemp, setTranslateTemp] = useState(String(initial.translate_temperature));
  const [evaluateTemp, setEvaluateTemp] = useState(String(initial.evaluate_temperature));
  const [ollamaHost, setOllamaHost] = useState(initial.ollama_host ?? "");

  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [deeplKey, setDeeplKey] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const [saved, setSaved] = useState<SavedState>({ kind: "idle" });

  useEffect(() => {
    setPrimaryProvider(initial.primary_provider);
    setFallbackChain(initial.fallback_chain);
    setOpenrouterModel(initial.openrouter_model);
    setTranslateTemp(String(initial.translate_temperature));
    setEvaluateTemp(String(initial.evaluate_temperature));
    setOllamaHost(initial.ollama_host ?? "");
  }, [initial]);

  // Clear the "Saved" badge after 3s so it doesn't linger forever.
  useEffect(() => {
    if (saved.kind !== "saved") return;
    const t = setTimeout(() => setSaved({ kind: "idle" }), 3000);
    return () => clearTimeout(t);
  }, [saved]);

  const mutation = useMutation({
    mutationFn: (body: AppSettingsUpdate) => api.appSettings.update(body),
    onSuccess: () => {
      setSaved({ kind: "saved", at: new Date() });
      setAnthropicKey("");
      setOpenaiKey("");
      setOpenrouterKey("");
      setDeeplKey("");
      setTouched({});
      onSaved();
    },
    onError: (err) => {
      const message = err instanceof ApiError ? String(err.detail) : (err as Error).message;
      setSaved({ kind: "error", message });
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const body: AppSettingsUpdate = {};

    if (primaryProvider !== initial.primary_provider) body.primary_provider = primaryProvider;

    if (fallbackChain.join(",") !== initial.fallback_chain.join(",")) {
      body.fallback_chain = fallbackChain;
    }
    if (openrouterModel !== initial.openrouter_model) body.openrouter_model = openrouterModel;

    const tTemp = Number(translateTemp);
    if (Number.isFinite(tTemp) && tTemp !== initial.translate_temperature) {
      body.translate_temperature = tTemp;
    }
    const eTemp = Number(evaluateTemp);
    if (Number.isFinite(eTemp) && eTemp !== initial.evaluate_temperature) {
      body.evaluate_temperature = eTemp;
    }
    if (ollamaHost !== (initial.ollama_host ?? "")) {
      body.ollama_host = ollamaHost === "" ? null : ollamaHost;
    }

    if (touched.anthropic) body.anthropic_api_key = anthropicKey;
    if (touched.openai) body.openai_api_key = openaiKey;
    if (touched.openrouter) body.openrouter_api_key = openrouterKey;
    if (touched.deepl) body.deepl_api_key = deeplKey;

    mutation.mutate(body);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl flex flex-col gap-6"
    >
      <Section
        title="Primary provider"
        description="Chosen first for every translate and evaluate call. Falls back to the chain below on errors."
      >
        <Select
          value={primaryProvider}
          onValueChange={(v) => setPrimaryProvider(typeof v === "string" ? v : "anthropic")}
        >
          <SelectTrigger size="sm" className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROVIDERS.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>

      <Section
        title="Fallback chain"
        description="Tried in order when the primary fails. Drag to reorder, or use the arrows."
      >
        <FallbackChainEditor value={fallbackChain} onChange={setFallbackChain} />
      </Section>

      <Section
        title="API keys"
        description="Stored encrypted at rest. Empty submit on a key clears that provider; existing keys stay until replaced."
      >
        <div className="flex flex-col gap-4">
          <KeyInput
            label="Anthropic"
            hasKey={initial.has_anthropic_key}
            value={anthropicKey}
            onChange={(v) => {
              setAnthropicKey(v);
              setTouched((t) => ({ ...t, anthropic: true }));
            }}
          />
          <KeyInput
            label="OpenAI"
            hasKey={initial.has_openai_key}
            value={openaiKey}
            onChange={(v) => {
              setOpenaiKey(v);
              setTouched((t) => ({ ...t, openai: true }));
            }}
          />
          <KeyInput
            label="OpenRouter"
            hasKey={initial.has_openrouter_key}
            value={openrouterKey}
            onChange={(v) => {
              setOpenrouterKey(v);
              setTouched((t) => ({ ...t, openrouter: true }));
            }}
          />
          <KeyInput
            label="DeepL"
            hasKey={initial.has_deepl_key}
            value={deeplKey}
            onChange={(v) => {
              setDeeplKey(v);
              setTouched((t) => ({ ...t, deepl: true }));
            }}
          />
        </div>
      </Section>

      <Section
        title="OpenRouter model"
        description={
          <>
            Model string passed to OpenRouter. Free models rotate weekly —{" "}
            <a
              href="https://openrouter.ai/models?q=:free"
              target="_blank"
              rel="noreferrer"
              className="text-flame-soft hover:underline"
            >
              browse the current roster
            </a>
            .
          </>
        }
      >
        <Input
          value={openrouterModel}
          onChange={(e) => setOpenrouterModel(e.target.value)}
          placeholder="google/gemini-2.0-flash-exp:free"
          className="font-mono text-[12.5px]"
        />
      </Section>

      <Section
        title="Temperatures"
        description="Sampling temperature for translate and evaluate calls. 0.0 is deterministic — use it unless you're prompting variations."
      >
        <div className="flex gap-4">
          <div className="flex flex-col gap-1.5">
            <Label
              htmlFor="translate-temp"
              className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-text-muted"
            >
              Translate
            </Label>
            <Input
              id="translate-temp"
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={translateTemp}
              onChange={(e) => setTranslateTemp(e.target.value)}
              className="w-28 font-mono text-[12.5px]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label
              htmlFor="evaluate-temp"
              className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-text-muted"
            >
              Evaluate
            </Label>
            <Input
              id="evaluate-temp"
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={evaluateTemp}
              onChange={(e) => setEvaluateTemp(e.target.value)}
              className="w-28 font-mono text-[12.5px]"
            />
          </div>
        </div>
      </Section>

      <Section
        title="Ollama host"
        description="Optional. Where your local Ollama daemon listens. Defaults to http://localhost:11434."
      >
        <Input
          value={ollamaHost}
          onChange={(e) => setOllamaHost(e.target.value)}
          placeholder="http://localhost:11434"
          className="font-mono text-[12.5px]"
        />
      </Section>

      <div className="flex items-center justify-end gap-3 pt-4 border-t border-line/70">
        {saved.kind === "saved" ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium bg-mint/15 text-mint border border-mint/30">
            <CheckIcon className="size-3" />
            Saved
          </span>
        ) : null}
        {saved.kind === "error" ? (
          <span className="text-[12px] text-status-rejected">{saved.message}</span>
        ) : null}
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </form>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>
        {description ? (
          <p className="text-[12.5px] text-text-soft max-w-prose">{description}</p>
        ) : null}
      </div>
      <Card>
        <CardContent className="p-4 flex flex-col gap-3">{children}</CardContent>
      </Card>
    </section>
  );
}

/* ---------------------------------------------------------------------------
 * Fallback chain editor — sortable chip list.
 *
 * Comma-separated text input made the chain order brittle (typos + re-typing
 * to reorder). Each provider is now a chip with native HTML5 drag-and-drop
 * for mouse reorder + ↑/↓ buttons for keyboard accessibility + × to remove.
 * "+ Add" opens a small Select of providers not yet in the chain.
 *
 * The list of available providers comes from the same PROVIDERS const used
 * by the Primary provider Select, so the two stay in sync.
 * ------------------------------------------------------------------------ */
function FallbackChainEditor({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);

  const available = PROVIDERS.filter((p) => !value.includes(p));

  function move(from: number, to: number) {
    if (to < 0 || to >= value.length || from === to) return;
    const next = [...value];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  }

  function remove(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  function add(p: string) {
    if (value.includes(p)) return;
    onChange([...value, p]);
  }

  return (
    <div className="flex flex-col gap-2">
      {value.length === 0 ? (
        <p className="text-[12.5px] text-text-muted italic">
          No fallback providers. The primary will fail loudly on errors.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {value.map((p, idx) => (
            <li
              key={p}
              draggable
              onDragStart={() => setDragIdx(idx)}
              onDragOver={(e) => {
                e.preventDefault();
                setOverIdx(idx);
              }}
              onDragEnd={() => {
                setDragIdx(null);
                setOverIdx(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                if (dragIdx !== null && dragIdx !== idx) move(dragIdx, idx);
                setDragIdx(null);
                setOverIdx(null);
              }}
              className={`group flex items-center gap-2 rounded-md border bg-card pl-2 pr-1 py-1.5 transition-colors ${
                overIdx === idx && dragIdx !== null && dragIdx !== idx
                  ? "border-flame/45 bg-flame/5"
                  : "border-line hover:border-line-strong"
              } ${dragIdx === idx ? "opacity-40" : ""}`}
            >
              <span
                aria-hidden
                className="cursor-grab active:cursor-grabbing text-text-muted hover:text-text-soft"
              >
                <GripVerticalIcon className="size-3.5" />
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted w-5">
                {idx + 1}
              </span>
              <span className="font-mono text-[12.5px] text-foreground flex-1">{p}</span>
              <button
                type="button"
                onClick={() => move(idx, idx - 1)}
                disabled={idx === 0}
                className="size-6 inline-flex items-center justify-center rounded text-text-muted hover:text-foreground hover:bg-ink-2 disabled:opacity-30 disabled:hover:bg-transparent"
                aria-label={`Move ${p} up`}
              >
                <ArrowUpIcon className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => move(idx, idx + 1)}
                disabled={idx === value.length - 1}
                className="size-6 inline-flex items-center justify-center rounded text-text-muted hover:text-foreground hover:bg-ink-2 disabled:opacity-30 disabled:hover:bg-transparent"
                aria-label={`Move ${p} down`}
              >
                <ArrowDownIcon className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => remove(idx)}
                className="size-6 inline-flex items-center justify-center rounded text-text-muted hover:text-status-rejected hover:bg-status-rejected/10"
                aria-label={`Remove ${p}`}
              >
                <XIcon className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {available.length > 0 ? (
        <div className="flex items-center gap-2 pt-1">
          <Select value="" onValueChange={(v) => v && add(typeof v === "string" ? v : "")}>
            <SelectTrigger size="sm" className="w-48">
              <SelectValue placeholder="Add a provider…" />
            </SelectTrigger>
            <SelectContent>
              {available.map((p) => (
                <SelectItem key={p} value={p}>
                  <span className="font-mono text-[12.5px]">{p}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-[11.5px] text-text-muted inline-flex items-center gap-1">
            <PlusIcon className="size-3" />
            to extend the chain
          </span>
        </div>
      ) : (
        <p className="text-[11.5px] text-text-muted">
          Every provider is in the chain. Remove one to add a different order.
        </p>
      )}
    </div>
  );
}

function KeyInput({
  label,
  hasKey,
  value,
  onChange,
}: {
  label: string;
  hasKey: boolean;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-text-muted">
          {label}
        </Label>
        <StatusPill set={hasKey} />
      </div>
      <Input
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={hasKey ? "••••••••  (replace or leave blank)" : ""}
        className="font-mono text-[12.5px]"
      />
    </div>
  );
}

function StatusPill({ set }: { set: boolean }) {
  if (set) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-[0.08em] bg-mint/15 text-mint border border-mint/30">
        <span className="size-1 rounded-full bg-mint" />
        set
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-[0.08em] bg-ink-2 text-text-muted border border-line">
      <span className="size-1 rounded-full bg-text-muted" />
      not set
    </span>
  );
}

function FormSkeleton() {
  return (
    <div className="px-6 py-10 sm:px-8 sm:py-12 max-w-3xl flex flex-col gap-6">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex flex-col gap-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-64" />
          <Skeleton className="h-16 w-full" />
        </div>
      ))}
    </div>
  );
}
