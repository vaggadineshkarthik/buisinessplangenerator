"use client";

import { FileText } from "lucide-react";
import * as React from "react";

import { EmptyState, Spinner } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { getDocumentChunks } from "@/lib/api";
import type { ChunkRecord } from "@/lib/types";

interface DocumentPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  documentName?: string;
  totalChunks?: number;
}

export function DocumentPreviewDialog({
  open,
  onOpenChange,
  documentId,
  documentName,
  totalChunks,
}: DocumentPreviewDialogProps) {
  const [chunks, setChunks] = React.useState<ChunkRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open || !documentId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDocumentChunks(documentId, 100, 0)
      .then((data) => {
        if (!cancelled) setChunks(data.chunks);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, documentId]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={documentName ?? "Document preview"}
      description={
        totalChunks !== undefined
          ? `${totalChunks} indexed chunk${totalChunks === 1 ? "" : "s"}`
          : "Indexed chunks and page references"
      }
    >
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
          <Spinner /> Loading chunks…
        </div>
      ) : error ? (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      ) : chunks.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title="No chunks available"
          description="This document has not been processed into chunks yet."
        />
      ) : (
        <ul className="space-y-3">
          {chunks.map((chunk) => (
            <li
              key={chunk.id}
              className="rounded-lg border border-border bg-secondary/20 p-3"
            >
              <div className="mb-2 flex items-center gap-2">
                <Badge variant="secondary">Chunk {chunk.chunk_index + 1}</Badge>
                {chunk.page_number > 0 && (
                  <Badge variant="outline">Page {chunk.page_number}</Badge>
                )}
                <span className="ml-auto text-[11px] text-muted-foreground">
                  ~{chunk.token_estimate} tokens
                </span>
              </div>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                {chunk.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
