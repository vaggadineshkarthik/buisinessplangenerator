"use client";

import {
  Building2,
  CalendarDays,
  Download,
  FileText,
  RefreshCw,
  Trash2,
} from "lucide-react";
import * as React from "react";

import { Markdown } from "@/components/chat/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/shared/states";
import { planExportUrl } from "@/lib/api";
import type { Citation, PlanDetail, PlanSectionRecord } from "@/lib/types";
import { cn, formatDate, formatNumber } from "@/lib/utils";

function statusVariant(status: string) {
  switch (status) {
    case "ready":
      return "success" as const;
    case "generating":
      return "warning" as const;
    case "error":
      return "danger" as const;
    default:
      return "secondary" as const;
  }
}

function uniqueCitations(sections: PlanSectionRecord[]): Citation[] {
  const seen = new Map<string, Citation>();
  for (const section of sections) {
    for (const citation of section.citations ?? []) {
      const key = `${citation.document_name}-${citation.page_number}`;
      if (!seen.has(key)) seen.set(key, citation);
    }
  }
  return [...seen.values()];
}

interface PlanViewProps {
  plan: PlanDetail;
  onRegenerate?: () => void;
  onDelete?: () => void;
  busy?: boolean;
  className?: string;
}

export function PlanView({
  plan,
  onRegenerate,
  onDelete,
  busy,
  className,
}: PlanViewProps) {
  const written = plan.sections.filter((section) => section.content?.trim());
  const sources = React.useMemo(() => uniqueCitations(plan.sections), [plan.sections]);

  return (
    <div className={cn("space-y-5", className)}>
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight">{plan.title}</h2>
              <Badge variant={statusVariant(plan.status)}>{plan.status}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Building2 className="h-3.5 w-3.5" />
                {plan.business_name}
                {plan.industry ? ` · ${plan.industry}` : ""}
              </span>
              <span className="flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" />
                {written.length}/{plan.sections.length} sections ·{" "}
                {formatNumber(plan.word_count)} words
              </span>
              <span className="flex items-center gap-1.5">
                <CalendarDays className="h-3.5 w-3.5" />
                {formatDate(plan.created_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm" disabled={busy}>
              <a href={planExportUrl(plan.id, "markdown")} download>
                <Download className="h-3.5 w-3.5" />
                Markdown
              </a>
            </Button>
            <Button asChild variant="outline" size="sm" disabled={busy}>
              <a href={planExportUrl(plan.id, "text")} download>
                <Download className="h-3.5 w-3.5" />
                Text
              </a>
            </Button>
            {onRegenerate && (
              <Button variant="secondary" size="sm" onClick={onRegenerate} disabled={busy}>
                {busy ? <Spinner className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Regenerate
              </Button>
            )}
            {onDelete && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onDelete}
                disabled={busy}
                className="text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            )}
          </div>
        </div>

        {plan.error && (
          <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-muted-foreground">
            {plan.error}
          </p>
        )}

        {sources.length > 0 && (
          <div className="mt-4 border-t border-border pt-4">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Grounded in {sources.length} source{sources.length === 1 ? "" : "s"}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {sources.map((citation) => (
                <Badge key={`${citation.document_name}-${citation.page_number}`} variant="outline">
                  {citation.label}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>

      {written.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-6 py-10 text-center text-sm text-muted-foreground">
          This plan has no written sections yet.
        </p>
      ) : (
        <div className="space-y-4">
          {plan.sections
            .filter((section) => section.content?.trim())
            .map((section) => (
              <section
                key={section.key}
                id={`section-${section.key}`}
                className="rounded-xl border border-border bg-card p-5 shadow-sm"
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-base font-semibold tracking-tight">
                    {section.title}
                  </h3>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {formatNumber(section.word_count)} words
                  </span>
                </div>
                <Markdown content={section.content} />
                {section.citations?.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border pt-3">
                    {section.citations.map((citation) => (
                      <Badge key={citation.label} variant="secondary">
                        {citation.label}
                      </Badge>
                    ))}
                  </div>
                )}
              </section>
            ))}
        </div>
      )}

      <p className="px-1 text-[11px] text-muted-foreground">
        Figures marked as assumptions are illustrative and must be validated before use.
      </p>
    </div>
  );
}
