"use client";

import { FileText } from "lucide-react";

import { Markdown } from "@/components/chat/markdown";
import { Spinner } from "@/components/shared/states";
import type { PlanSectionMeta } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";

interface PlanLiveProps {
  title: string;
  sections: PlanSectionMeta[];
  content: Record<string, string>;
  activeKey: string | null;
  wordCount: number;
  className?: string;
}

/** Live preview of a plan while the backend streams each section. */
export function PlanLive({
  title,
  sections,
  content,
  activeKey,
  wordCount,
  className,
}: PlanLiveProps) {
  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-5 py-3.5 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-medium">
          <FileText className="h-4 w-4 text-primary" />
          {title}
        </div>
        <span className="text-xs text-muted-foreground">
          {formatNumber(wordCount)} words · {sections.length} section
          {sections.length === 1 ? "" : "s"}
        </span>
      </div>

      {sections.map((section) => {
        const body = content[section.key] ?? "";
        const isActive = activeKey === section.key;
        if (!body && !isActive) return null;
        return (
          <section
            key={section.key}
            className={cn(
              "rounded-xl border bg-card p-5 shadow-sm transition-colors",
              isActive ? "border-primary/40" : "border-border",
            )}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-base font-semibold tracking-tight">{section.title}</h3>
              {isActive && <Spinner className="h-3.5 w-3.5 text-primary" />}
            </div>
            {body ? (
              <Markdown content={body} />
            ) : (
              <p className="text-sm text-muted-foreground">Writing…</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
