"use client";

import { Database, ShieldCheck, ShieldAlert, ShieldX, Sigma } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  RelevanceEvaluation,
  RetrievedChunk,
  RetrievalStats,
  VerificationResult,
} from "@/lib/types";

interface ContextPanelProps {
  contexts: RetrievedChunk[];
  verification?: VerificationResult | null;
  relevance?: RelevanceEvaluation | null;
  retrieval?: RetrievalStats | null;
  activeKey?: string | null;
  onSelectChunk?: (chunk: RetrievedChunk) => void;
  className?: string;
}

const VERDICT: Record<
  VerificationResult["verdict"],
  { label: string; variant: "success" | "warning" | "danger" | "secondary"; icon: typeof ShieldCheck }
> = {
  verified: { label: "Verified", variant: "success", icon: ShieldCheck },
  partially_verified: { label: "Partially verified", variant: "warning", icon: ShieldAlert },
  unverified: { label: "Unverified", variant: "danger", icon: ShieldX },
  no_sources: { label: "No sources", variant: "secondary", icon: Database },
};

export function ContextPanel({
  contexts,
  verification,
  relevance,
  retrieval,
  activeKey,
  onSelectChunk,
  className,
}: ContextPanelProps) {
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="border-b border-border p-4">
        <h2 className="text-sm font-semibold">Retrieved context</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {retrieval
            ? `${retrieval.returned} of ${retrieval.candidates} candidates kept · threshold ${retrieval.threshold}`
            : "Chunks used to ground the answer"}
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {verification && (
          <div className="rounded-lg border border-border bg-secondary/30 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Answer verification
              </span>
              <VerdictBadge verdict={verification.verdict} />
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Sigma className="h-3 w-3" />
              {Math.round((verification.coverage || 0) * 100)}% of claims supported by
              sources
            </div>
            {verification.disclaimer && (
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground/80">
                {verification.disclaimer}
              </p>
            )}
          </div>
        )}

        {relevance && (
          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Relevance: </span>
            {relevance.relevant ? "sufficient context found" : "weak context"} · top{" "}
            {Math.round((relevance.top_score || 0) * 100)}%
            {relevance.reason ? ` — ${relevance.reason}` : ""}
          </div>
        )}

        {contexts.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
            No retrieved chunks yet. Ask a question to see the context.
          </p>
        ) : (
          <ul className="space-y-3">
            {contexts.map((chunk) => {
              const key = `${chunk.document_id}:${chunk.chunk_index}`;
              const active = activeKey === key;
              return (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => onSelectChunk?.(chunk)}
                    className={cn(
                      "w-full rounded-lg border p-3 text-left transition-colors",
                      active
                        ? "border-primary/50 bg-primary/5"
                        : "border-border bg-card hover:border-primary/30",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-medium">
                        {chunk.document_name}
                      </span>
                      <Badge variant="secondary" className="shrink-0">
                        {chunk.page_number > 0
                          ? `Page ${chunk.page_number}`
                          : `Chunk ${chunk.chunk_index + 1}`}
                      </Badge>
                    </div>
                    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                        style={{
                          width: `${Math.max(4, Math.round((chunk.similarity || 0) * 100))}%`,
                        }}
                      />
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>Similarity {Math.round((chunk.similarity || 0) * 100)}%</span>
                      <span>Rerank {Math.round((chunk.rerank_score || 0) * 100)}%</span>
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
                      {chunk.content}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: VerificationResult["verdict"] }) {
  const config = VERDICT[verdict] ?? VERDICT.no_sources;
  const Icon = config.icon;
  return (
    <Badge variant={config.variant}>
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}
