"use client";

import { Check, Loader2 } from "lucide-react";

import type { StageEventData } from "@/lib/types";
import { cn } from "@/lib/utils";

export const PLAN_STAGES: { key: string; label: string }[] = [
  { key: "analyzing", label: "Analysing your inputs" },
  { key: "embedding", label: "Embedding research query" },
  { key: "searching", label: "Searching research documents" },
  { key: "generating", label: "Writing sections" },
  { key: "citations", label: "Preparing citations" },
];

export type PlanStageStatus = "pending" | "active" | "done";

/** Derive per-stage statuses from the streamed plan stage events. */
export function reducePlanStages(
  events: StageEventData[],
): Record<string, PlanStageStatus> {
  const statuses: Record<string, PlanStageStatus> = {};
  for (const event of events) {
    if (!PLAN_STAGES.some((stage) => stage.key === event.name)) continue;
    statuses[event.name] = event.status === "completed" ? "done" : "active";
  }
  return statuses;
}

interface PlanStagesProps {
  statuses: Record<string, PlanStageStatus>;
  activeLabel?: string | null;
  className?: string;
}

/**
 * Live view of the business-plan workflow. Statuses only change when the
 * backend streams a real stage event — nothing here is timer driven.
 */
export function PlanStages({ statuses, activeLabel, className }: PlanStagesProps) {
  const visible = PLAN_STAGES.filter((stage) => statuses[stage.key]);

  return (
    <div className={cn("space-y-2", className)}>
      {(visible.length ? visible : PLAN_STAGES).map((stage) => {
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
            <span className={cn(status === "pending" ? "text-muted-foreground" : "text-foreground")}>
              {stage.label}
              {status === "active" && activeLabel ? ` — ${activeLabel}` : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
