"use client";

import { AlertTriangle, FileText, Plus, Square, Trash2 } from "lucide-react";
import * as React from "react";

import { PlanLive } from "@/components/plan/plan-live";
import { PlanStages, reducePlanStages } from "@/components/plan/plan-stages";
import { PlanView } from "@/components/plan/plan-view";
import { PlanWizard } from "@/components/plan/plan-wizard";
import { ConfigBanner } from "@/components/shared/config-banner";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, Spinner } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  deletePlan,
  getHealth,
  getPlan,
  getPlanCatalog,
  listDocuments,
  listPlans,
  regeneratePlan,
  streamPlan,
} from "@/lib/api";
import type {
  DocumentRecord,
  PlanCatalogSection,
  PlanDetail,
  PlanGenerateInput,
  PlanSectionMeta,
  PlanSectionRecord,
  PlanStreamCallbacks,
  PlanSummary,
  StageEventData,
} from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

type Mode = "form" | "live" | "plan";

interface PlanDraft {
  planId: string;
  title: string;
  sections: PlanSectionMeta[];
  content: Record<string, string>;
}

function countWords(text: string): number {
  const matches = text.match(/\S+/g);
  return matches ? matches.length : 0;
}

export default function PlanPage() {
  const { toast } = useToast();

  const [mode, setMode] = React.useState<Mode>("form");
  const [online, setOnline] = React.useState(true);
  const [configured, setConfigured] = React.useState(true);

  const [catalog, setCatalog] = React.useState<PlanCatalogSection[]>([]);
  const [documents, setDocuments] = React.useState<DocumentRecord[]>([]);
  const [savedPlans, setSavedPlans] = React.useState<PlanSummary[]>([]);

  const [plan, setPlan] = React.useState<PlanDetail | null>(null);
  const [draft, setDraft] = React.useState<PlanDraft | null>(null);
  const [stageEvents, setStageEvents] = React.useState<StageEventData[]>([]);
  const [activeKey, setActiveKey] = React.useState<string | null>(null);
  const [activeTitle, setActiveTitle] = React.useState<string | null>(null);
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [statusNote, setStatusNote] = React.useState<string | null>(null);
  const [loadingPlan, setLoadingPlan] = React.useState(false);

  const abortRef = React.useRef<AbortController | null>(null);

  const stageStatuses = React.useMemo(
    () => reducePlanStages(stageEvents),
    [stageEvents],
  );

  const liveWords = React.useMemo(
    () => (draft ? countWords(Object.values(draft.content).join(" ")) : 0),
    [draft],
  );

  const refreshSaved = React.useCallback(async () => {
    try {
      const plans = await listPlans();
      setSavedPlans(plans);
    } catch {
      /* the sidebar list is best-effort */
    }
  }, []);

  const bootstrap = React.useCallback(async () => {
    // Loaded independently: the wizard must still render if any single request
    // fails, otherwise the form (and its inputs) would never appear.
    const [health, sectionCatalog, docs, plans] = await Promise.allSettled([
      getHealth(),
      getPlanCatalog(),
      listDocuments(),
      listPlans(),
    ]);

    if (health.status === "fulfilled") {
      setOnline(health.value.status === "ok");
      setConfigured(health.value.openrouter_configured);
    } else {
      setOnline(false);
      toast({
        title: "Cannot reach the RAGify AI backend",
        description: (health.reason as Error).message,
        variant: "error",
      });
    }
    if (sectionCatalog.status === "fulfilled") {
      setCatalog(sectionCatalog.value.sections);
    }
    if (docs.status === "fulfilled") {
      setDocuments(docs.value);
    }
    if (plans.status === "fulfilled") {
      setSavedPlans(plans.value);
    }
  }, [toast]);

  React.useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const runStream = React.useCallback(
    async (
      start: (
        callbacks: PlanStreamCallbacks,
        signal: AbortSignal,
      ) => Promise<void>,
    ) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStageEvents([]);
      setStatusNote(null);
      setActiveKey(null);
      setActiveTitle(null);

      const callbacks: PlanStreamCallbacks = {
        onPlan: (data) => {
          setDraft({
            planId: data.plan_id,
            title: data.title,
            sections: data.sections,
            content: {},
          });
          setMode("live");
        },
        onStage: (data) => {
          setStageEvents((current) => [...current, data]);
          const detail = data.detail as
            | { section_key?: string; title?: string }
            | undefined;
          if (data.name === "generating" && data.status === "started" && detail?.section_key) {
            setActiveKey(detail.section_key);
            setActiveTitle(detail.title ?? null);
          }
        },
        onToken: (text, sectionKey) => {
          if (!sectionKey) return;
          setDraft((current) =>
            current
              ? {
                  ...current,
                  content: {
                    ...current.content,
                    [sectionKey]: (current.content[sectionKey] ?? "") + text,
                  },
                }
              : current,
          );
        },
        onSection: (data: PlanSectionRecord) => {
          setDraft((current) =>
            current
              ? { ...current, content: { ...current.content, [data.key]: data.content } }
              : current,
          );
          setActiveKey(null);
          setActiveTitle(null);
        },
        onError: (data) => setStatusNote(data.message),
        onResult: (data) => {
          setPlan(data);
          setDraft(null);
          setMode("plan");
          refreshSaved();
        },
        onDone: () => undefined,
      };

      try {
        await start(callbacks, controller.signal);
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          const message = (error as Error).message;
          setStatusNote(message);
          toast({
            title: "Plan generation failed",
            description: message,
            variant: "error",
          });
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
        refreshSaved();
      }
    },
    [refreshSaved, toast],
  );

  const generate = (payload: PlanGenerateInput) => {
    runStream((callbacks, signal) => streamPlan(payload, callbacks, signal));
  };

  const regenerate = (target: PlanDetail) => {
    if (isStreaming) return;
    setPlan(target);
    runStream((callbacks, signal) => regeneratePlan(target.id, callbacks, signal));
  };

  const stop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  const loadPlan = async (id: string) => {
    if (isStreaming) return;
    setLoadingPlan(true);
    try {
      const detail = await getPlan(id);
      setPlan(detail);
      setMode("plan");
      setStatusNote(null);
    } catch (error) {
      toast({
        title: "Could not open plan",
        description: (error as Error).message,
        variant: "error",
      });
    } finally {
      setLoadingPlan(false);
    }
  };

  const removePlan = async (planId: string) => {
    setBusy(true);
    try {
      await deletePlan(planId);
      toast({ title: "Plan deleted", variant: "success" });
      if (plan?.id === planId) {
        setPlan(null);
        setMode("form");
      }
      refreshSaved();
    } catch (error) {
      toast({
        title: "Could not delete plan",
        description: (error as Error).message,
        variant: "error",
      });
    } finally {
      setBusy(false);
    }
  };

  const startNew = () => {
    if (isStreaming) return;
    setPlan(null);
    setDraft(null);
    setStageEvents([]);
    setStatusNote(null);
    setMode("form");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Business Plan Generator"
        description="Describe your business and RAGify AI writes an investor-ready plan section by section — grounded in your research documents."
        actions={
          mode !== "form" ? (
            <Button variant="outline" size="sm" onClick={startNew} disabled={isStreaming}>
              <Plus className="h-3.5 w-3.5" />
              New plan
            </Button>
          ) : null
        }
      />

      <ConfigBanner configured={configured} online={online} />

      {statusNote && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
          {statusNote}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-5">
          {mode === "form" && (
            <PlanWizard
              catalog={catalog}
              documents={documents}
              onSubmit={generate}
              busy={isStreaming}
              configured={configured}
            />
          )}

          {mode === "live" && draft && (
            <>
              <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Spinner className="h-3.5 w-3.5 text-primary" />
                    {activeTitle
                      ? `Writing “${activeTitle}”…`
                      : "Generating your business plan…"}
                  </div>
                  <Button variant="destructive" size="sm" onClick={stop}>
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                </div>
                <PlanStages statuses={stageStatuses} activeLabel={activeTitle} />
              </div>
              <PlanLive
                title={draft.title}
                sections={draft.sections}
                content={draft.content}
                activeKey={activeKey}
                wordCount={liveWords}
              />
            </>
          )}

          {mode === "live" && !draft && (
            <div className="flex items-center justify-center rounded-xl border border-border bg-card py-16 text-sm text-muted-foreground">
              <Spinner className="mr-2" /> Starting generation…
            </div>
          )}

          {mode === "plan" && plan && (
            <>
              {loadingPlan && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Spinner className="h-3.5 w-3.5" /> Loading…
                </div>
              )}
              <PlanView
                plan={plan}
                busy={isStreaming || busy}
                onRegenerate={() => regenerate(plan)}
                onDelete={() => removePlan(plan.id)}
              />
            </>
          )}
        </div>

        <aside className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Saved plans</h2>
            <Badge variant="secondary">{savedPlans.length}</Badge>
          </div>
          {savedPlans.length === 0 ? (
            <EmptyState
              className="px-4 py-8"
              icon={<FileText className="h-4 w-4" />}
              title="No plans yet"
              description="Generated plans are saved here automatically."
            />
          ) : (
            <ul className="space-y-2">
              {savedPlans.map((saved) => (
                <li key={saved.id}>
                  <div
                    className={cn(
                      "group rounded-lg border p-3 transition-colors",
                      plan?.id === saved.id
                        ? "border-primary/40 bg-primary/5"
                        : "border-border bg-card hover:bg-secondary/50",
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => loadPlan(saved.id)}
                        className="min-w-0 flex-1 text-left"
                        disabled={isStreaming}
                      >
                        <p className="truncate text-sm font-medium">{saved.title}</p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          {saved.section_count} sections · {saved.word_count} words ·{" "}
                          {relativeTime(saved.updated_at)}
                        </p>
                      </button>
                      <button
                        type="button"
                        onClick={() => removePlan(saved.id)}
                        className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                        aria-label="Delete plan"
                        disabled={busy}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <Badge
                        variant={
                          saved.status === "ready"
                            ? "success"
                            : saved.status === "error"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {saved.status}
                      </Badge>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
