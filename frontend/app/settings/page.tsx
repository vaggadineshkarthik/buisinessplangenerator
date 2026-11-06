"use client";

import {
  Activity,
  Cpu,
  Database,
  RefreshCw,
  Save,
  Settings2,
  Sparkles,
} from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/shared/page-header";
import { ErrorState, LoadingState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { getDiagnostics, getModels, getSettings, updateSettings } from "@/lib/api";
import type { SettingsValues } from "@/lib/types";

const EMBEDDING_MODELS = [
  "BAAI/bge-small-en-v1.5",
  "all-MiniLM-L6-v2",
];

export default function SettingsPage() {
  const { toast } = useToast();
  const [values, setValues] = React.useState<SettingsValues | null>(null);
  const [meta, setMeta] = React.useState<Awaited<ReturnType<typeof getSettings>> | null>(
    null,
  );
  const [models, setModels] = React.useState<{ id: string; name: string }[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [diagnostics, setDiagnostics] = React.useState<Record<string, unknown> | null>(
    null,
  );
  const [loadingDiagnostics, setLoadingDiagnostics] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const settings = await getSettings();
      setMeta(settings);
      setValues(settings.values);
      if (settings.openrouter.configured) {
        getModels()
          .then((result) => setModels(result.models.slice(0, 100)))
          .catch(() => setModels([]));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const update = (patch: Partial<SettingsValues>) =>
    setValues((current) => (current ? { ...current, ...patch } : current));

  const save = async () => {
    if (!values) return;
    setSaving(true);
    try {
      const result = await updateSettings(values);
      setValues(result.values);
      toast({
        title: "Settings saved",
        description: "Runtime configuration updated.",
        variant: "success",
      });
      await load();
    } catch (err) {
      toast({
        title: "Could not save settings",
        description: (err as Error).message,
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  const loadDiagnostics = async () => {
    setLoadingDiagnostics(true);
    try {
      setDiagnostics(await getDiagnostics());
    } catch (err) {
      toast({
        title: "Diagnostics failed",
        description: (err as Error).message,
        variant: "error",
      });
    } finally {
      setLoadingDiagnostics(false);
    }
  };

  if (loading) return <LoadingState label="Loading settings…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!values || !meta) return null;

  const configured = meta.openrouter.configured;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Settings"
        description="Configure the model, retrieval parameters and review system diagnostics."
        actions={
          <Button variant="gradient" size="sm" onClick={save} disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? "Saving…" : "Save changes"}
          </Button>
        }
      />

      {!configured && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              OpenRouter API key required
            </CardTitle>
            <CardDescription>
              Chat answers cannot be generated until a key is configured.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>1. Copy <code className="rounded bg-secondary px-1.5 py-0.5">.env.example</code> to <code className="rounded bg-secondary px-1.5 py-0.5">.env</code> in the project root.</p>
            <p>2. Set <code className="rounded bg-secondary px-1.5 py-0.5">OPENROUTER_API_KEY=sk-or-...</code> from openrouter.ai/keys.</p>
            <p>3. Restart the backend (uvicorn) so the key is picked up.</p>
            <p className="text-xs">
              The key is read from the environment on the server only and is never
              sent to this browser.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatusTile
          icon={<Cpu className="h-4 w-4" />}
          label="OpenRouter"
          ok={configured}
          value={configured ? "Configured" : "Not configured"}
          hint={meta.openrouter.model}
        />
        <StatusTile
          icon={<Sparkles className="h-4 w-4" />}
          label="Embeddings"
          ok
          value={meta.embeddings.model}
          hint={
            meta.embeddings.dimension
              ? `${meta.embeddings.dimension} dimensions`
              : meta.embeddings.loaded
                ? "Loaded"
                : "Lazy loaded"
          }
        />
        <StatusTile
          icon={<Database className="h-4 w-4" />}
          label="Vector store"
          ok={meta.vector_store.available}
          value={meta.vector_store.backend}
          hint={
            meta.vector_store.count !== undefined
              ? `${meta.vector_store.count} vectors`
              : meta.vector_store.error
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Model &amp; generation</CardTitle>
          <CardDescription>OpenRouter model and sampling parameters</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Model" className="sm:col-span-2">
            <Input
              list="openrouter-models"
              value={values.openrouter_model}
              onChange={(event) => update({ openrouter_model: event.target.value })}
              placeholder="openai/gpt-oss-120b"
            />
            <datalist id="openrouter-models">
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </datalist>
            {models.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Model list unavailable — type the model id manually.
              </p>
            )}
          </Field>
          <Field label="Temperature">
            <Input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={values.temperature}
              onChange={(event) => update({ temperature: Number(event.target.value) })}
            />
          </Field>
          <Field label="Max tokens">
            <Input
              type="number"
              min={16}
              max={8000}
              value={values.max_tokens}
              onChange={(event) => update({ max_tokens: Number(event.target.value) })}
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retrieval</CardTitle>
          <CardDescription>How chunks are searched and ranked</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Top K">
            <Input
              type="number"
              min={1}
              max={50}
              value={values.top_k}
              onChange={(event) => update({ top_k: Number(event.target.value) })}
            />
          </Field>
          <Field label="Similarity threshold">
            <Input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={values.similarity_threshold}
              onChange={(event) =>
                update({ similarity_threshold: Number(event.target.value) })
              }
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ingestion</CardTitle>
          <CardDescription>Chunking, embeddings and upload limits</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Chunk size (characters)">
            <Input
              type="number"
              min={200}
              max={4000}
              value={values.chunk_size}
              onChange={(event) => update({ chunk_size: Number(event.target.value) })}
            />
          </Field>
          <Field label="Chunk overlap (characters)">
            <Input
              type="number"
              min={0}
              max={2000}
              value={values.chunk_overlap}
              onChange={(event) =>
                update({ chunk_overlap: Number(event.target.value) })
              }
            />
          </Field>
          <Field label="Embedding model">
            <Select
              value={values.embedding_model}
              onChange={(event) => update({ embedding_model: event.target.value })}
            >
              {EMBEDDING_MODELS.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
              {!EMBEDDING_MODELS.includes(values.embedding_model) && (
                <option value={values.embedding_model}>{values.embedding_model}</option>
              )}
            </Select>
            <p className="text-xs text-muted-foreground">
              Changing the embedding model requires reprocessing documents.
            </p>
          </Field>
          <Field label="Max file size (MB)">
            <Input
              type="number"
              min={1}
              max={200}
              value={values.max_file_size_mb}
              onChange={(event) =>
                update({ max_file_size_mb: Number(event.target.value) })
              }
            />
          </Field>
          <Field label="Allowed extensions" className="sm:col-span-2">
            <div className="flex flex-wrap gap-1.5">
              {meta.uploads.allowed_extensions.map((extension) => (
                <Badge key={extension} variant="secondary">
                  .{extension}
                </Badge>
              ))}
            </div>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Diagnostics</CardTitle>
            <CardDescription>Live connectivity and storage checks</CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={loadDiagnostics}
            disabled={loadingDiagnostics}
          >
            <RefreshCw
              className={loadingDiagnostics ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
            />
            Run checks
          </Button>
        </CardHeader>
        <CardContent>
          {diagnostics ? (
            <pre className="max-h-80 overflow-auto rounded-lg border border-border bg-secondary/30 p-4 text-xs">
              {JSON.stringify(diagnostics, null, 2)}
            </pre>
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Activity className="h-4 w-4" />
              Run diagnostics to probe OpenRouter, embeddings, the vector store and the
              database.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`space-y-1.5 ${className ?? ""}`}>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function StatusTile({
  icon,
  label,
  value,
  hint,
  ok,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string | number;
  ok: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            {icon}
            {label}
          </span>
          <span
            className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`}
          />
        </div>
        <p className="truncate text-sm font-medium">{value}</p>
        {hint !== undefined && (
          <p className="truncate text-xs text-muted-foreground">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}
