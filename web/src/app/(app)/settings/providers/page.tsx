"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
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
 */
const PROVIDERS = ["anthropic", "openai", "openrouter", "ollama", "deepl"] as const;

export default function ProvidersPage() {
  const apiKey = typeof window !== "undefined" ? getApiKey() : null;
  if (!apiKey) {
    return (
      <div className="rounded-md border border-app-border bg-app-surface p-6 text-sm">
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
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900">
        Could not load app settings. The migration may not have run yet.
      </div>
    );
  }

  return <ProvidersFormBody initial={query.data} onSaved={() => qc.invalidateQueries({ queryKey: ["app-settings"] })} />;
}

type SavedState =
  | { kind: "idle" }
  | { kind: "saved"; at: Date }
  | { kind: "error"; message: string };

function ProvidersFormBody({ initial, onSaved }: { initial: AppSettings; onSaved: () => void }) {
  // The form mirrors the server's two distinct concerns: non-key fields
  // (round-tripped verbatim) and key fields (write-only, with a "set" /
  // "not set" status hint based on the boolean from the GET response).
  const [primaryProvider, setPrimaryProvider] = useState(initial.primary_provider);
  const [fallbackChain, setFallbackChain] = useState(initial.fallback_chain.join(", "));
  const [openrouterModel, setOpenrouterModel] = useState(initial.openrouter_model);
  const [translateTemp, setTranslateTemp] = useState(String(initial.translate_temperature));
  const [evaluateTemp, setEvaluateTemp] = useState(String(initial.evaluate_temperature));
  const [ollamaHost, setOllamaHost] = useState(initial.ollama_host ?? "");

  // Each key input maps to "leave alone" (untouched/never typed) vs "clear"
  // (typed then emptied) vs "set" (typed something). We track touched state
  // so a blank input that the user never touched is omitted from the PATCH.
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [deeplKey, setDeeplKey] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const [saved, setSaved] = useState<SavedState>({ kind: "idle" });

  // If the underlying data refreshes (e.g. after save), reset the displayed
  // non-key field values to the server's truth. Key fields stay blank.
  useEffect(() => {
    setPrimaryProvider(initial.primary_provider);
    setFallbackChain(initial.fallback_chain.join(", "));
    setOpenrouterModel(initial.openrouter_model);
    setTranslateTemp(String(initial.translate_temperature));
    setEvaluateTemp(String(initial.evaluate_temperature));
    setOllamaHost(initial.ollama_host ?? "");
  }, [initial]);

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

    const parsedChain = fallbackChain
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (parsedChain.join(",") !== initial.fallback_chain.join(",")) {
      body.fallback_chain = parsedChain;
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

    // Key fields: only send if the operator touched them. Typing then
    // emptying clears the provider; never-touching leaves it alone.
    if (touched.anthropic) body.anthropic_api_key = anthropicKey;
    if (touched.openai) body.openai_api_key = openaiKey;
    if (touched.openrouter) body.openrouter_api_key = openrouterKey;
    if (touched.deepl) body.deepl_api_key = deeplKey;

    mutation.mutate(body);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8 max-w-2xl">
      <Section title="Primary provider" description="The default provider for translate + evaluate calls.">
        <Select value={primaryProvider} onValueChange={setPrimaryProvider}>
          <SelectTrigger className="w-64">
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
        description="Comma-separated provider names. Tried in order if the primary fails."
      >
        <Input
          value={fallbackChain}
          onChange={(e) => setFallbackChain(e.target.value)}
          placeholder="anthropic, openai, ollama"
          className="w-full max-w-md"
        />
      </Section>

      <Section title="API keys" description="Empty submit on a key clears that provider. Existing keys stay until replaced.">
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
      </Section>

      <Section
        title="OpenRouter model"
        description={
          <>
            Model string passed to OpenRouter.{" "}
            <a
              href="https://openrouter.ai/models?q=:free"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Browse free models
            </a>
            .
          </>
        }
      >
        <Input
          value={openrouterModel}
          onChange={(e) => setOpenrouterModel(e.target.value)}
          placeholder="google/gemini-2.0-flash-exp:free"
          className="w-full max-w-md"
        />
      </Section>

      <Section title="Temperatures" description="Sampling temperature for translate / evaluate calls. 0.0 = deterministic.">
        <div className="flex gap-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor="translate-temp" className="text-xs text-app-text-secondary">
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
              className="w-28"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="evaluate-temp" className="text-xs text-app-text-secondary">
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
              className="w-28"
            />
          </div>
        </div>
      </Section>

      <Section title="Ollama host" description="Optional. Where your local Ollama daemon listens. Defaults to http://localhost:11434.">
        <Input
          value={ollamaHost}
          onChange={(e) => setOllamaHost(e.target.value)}
          placeholder="http://localhost:11434"
          className="w-full max-w-md"
        />
      </Section>

      <div className="flex items-center gap-4 pt-2 border-t border-app-border">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
        {saved.kind === "saved" && (
          <span className="text-sm text-app-text-secondary">
            Saved · {saved.at.toLocaleTimeString()}
          </span>
        )}
        {saved.kind === "error" && (
          <span className="text-sm text-red-700">Error: {saved.message}</span>
        )}
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
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description ? <p className="text-xs text-app-text-secondary mt-1">{description}</p> : null}
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
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
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between max-w-md">
        <Label className="text-xs text-app-text-secondary">{label}</Label>
        <span
          className={
            hasKey
              ? "text-xs text-emerald-700"
              : "text-xs text-app-text-secondary"
          }
        >
          {hasKey ? "set" : "not set"}
        </span>
      </div>
      <Input
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={hasKey ? "••••••••  (replace or leave blank)" : ""}
        className="w-full max-w-md"
      />
    </div>
  );
}

function FormSkeleton() {
  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}
