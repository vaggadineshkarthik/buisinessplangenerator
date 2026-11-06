"use client";

import { Check, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { StageEventData } from "@/lib/types";

export const WORKFLOW_STAGES: { key: string; label: string }[] = [
  { key: "analyzing", label: "Analyzing question" },
  { key: "embedding", label: "Generating query embedding" },
  { key: "searching", label: "Searching knowledge base" },
  { key: "evaluating", label: "Evaluating relevance" },
  { key: "reranking", label: "Reranking chunks" },
  { key: "context", label: "Building context" },
  { key: "generating", label: "Generating AI response" },
  { key: "verifying", label: "Verifying answer" },
  { key: "citations", label: "Preparing citations" },
];

export type StageStatus = "pending" | "active" | "done";

interface WorkflowStagesProps {
  statuses: Record<string, StageStatus>;
  className?: string;
}

/**
 * Live view of the actual LangGraph workflow events streamed from the backend.
 * Nothing here is timer-driven — statuses only change when the server says so.
 */
export function WorkflowStages({ statuses, className }: WorkflowStagesProps) {
  return (
    <div className={cn("space-y-2", className)}>
      {WORKFLOW_STAGES.map((stage) => {
        const status = statuses[stage.key] ?? "pending";
        return (
          <div key={stage.key} className="flex items-center gap-2.5 text-sm">
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                status === "done" &&
                  "border-emerald-500/40 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
                status === "active" && "border-primary/40 bg-primary/10 text-primary",
                status === "pending" && "border-border text-muted-foreground",
              )}
            >
              {status === "done" ? (
                <Check className="h-3 w-3" />
              ) : status === "active" ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <span className="h-1 w-1 rounded-full bg-current" />
              )}
            </span>
            <span
              className={cn(
                status === "pending" ? "text-muted-foreground" : "text-foreground",
              )}
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Derive per-stage statuses from the streamed stage events. */
export function reduceStages(
  events: StageEventData[],
): Record<string, StageStatus> {
  const statuses: Record<string, StageStatus> = {};
  for (const event of events) {
    if (!WORKFLOW_STAGES.some((stage) => stage.key === event.name)) continue;
    statuses[event.name] = event.status === "completed" ? "done" : "active";
  }
  return statuses;
}
