"use client";

import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Citation } from "@/lib/types";

export function citationKey(citation: Pick<Citation, "document_id" | "chunk_index">) {
  return `${citation.document_id}:${citation.chunk_index}`;
}

interface CitationChipProps {
  citation: Citation;
  active?: boolean;
  onClick?: (citation: Citation) => void;
}

/** Clickable source citation, e.g. "[Source: company_report.pdf, Page 4]". */
export function CitationChip({ citation, active, onClick }: CitationChipProps) {
  const page = citation.page_number > 0 ? ` · Page ${citation.page_number}` : "";
  return (
    <button
      type="button"
      onClick={() => onClick?.(citation)}
      title="Show the retrieved passage"
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-secondary/60 px-2 py-1 text-xs transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary",
        active && "border-primary/40 bg-primary/10 text-primary",
      )}
    >
      <FileText className="h-3 w-3 shrink-0" />
      <span className="truncate">
        {citation.document_name}
        {page}
      </span>
      {citation.similarity > 0 && (
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {Math.round(citation.similarity * 100)}%
        </span>
      )}
    </button>
  );
}
