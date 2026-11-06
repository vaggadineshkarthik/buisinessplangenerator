"use client";

import {
  Eye,
  FileSpreadsheet,
  FileText,
  FileType2,
  FileType,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { DocumentPreviewDialog } from "@/components/documents/document-preview-dialog";
import { DocumentStatusBadge } from "@/components/shared/document-status-badge";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { deleteDocument, listDocuments, reprocessDocument } from "@/lib/api";
import type { DocumentRecord, DocumentStatus } from "@/lib/types";
import { formatBytes, formatDate, formatNumber } from "@/lib/utils";

const TYPE_ICONS: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: FileType2,
  txt: FileType,
  csv: FileSpreadsheet,
};

export default function DocumentsPage() {
  const { toast } = useToast();
  const [documents, setDocuments] = React.useState<DocumentRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<"all" | DocumentStatus>("all");
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [previewId, setPreviewId] = React.useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<DocumentRecord | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDocuments(await listDocuments());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  // Poll while any document is still processing so status updates live.
  React.useEffect(() => {
    if (!documents.some((doc) => doc.status === "processing")) return;
    const timer = window.setInterval(load, 4000);
    return () => window.clearInterval(timer);
  }, [documents, load]);

  const filtered = documents.filter((doc) => {
    const matchesQuery = doc.name.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = statusFilter === "all" || doc.status === statusFilter;
    return matchesQuery && matchesStatus;
  });

  const handleReprocess = async (doc: DocumentRecord) => {
    setBusyId(doc.id);
    try {
      await reprocessDocument(doc.id);
      toast({ title: "Reprocessing started", description: doc.name, variant: "info" });
      await load();
    } catch (err) {
      toast({
        title: "Reprocessing failed",
        description: (err as Error).message,
        variant: "error",
      });
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const doc = pendingDelete;
    setPendingDelete(null);
    setBusyId(doc.id);
    try {
      await deleteDocument(doc.id);
      setDocuments((current) => current.filter((item) => item.id !== doc.id));
      toast({ title: "Document deleted", description: doc.name, variant: "success" });
    } catch (err) {
      toast({
        title: "Delete failed",
        description: (err as Error).message,
        variant: "error",
      });
    } finally {
      setBusyId(null);
    }
  };

  const previewDoc = documents.find((doc) => doc.id === previewId) ?? null;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Knowledge Base"
        description="Manage your indexed documents, chunks and embeddings."
        actions={
          <Button asChild variant="gradient" size="sm">
            <Link href="/upload">
              <UploadCloud className="h-4 w-4" />
              Upload documents
            </Link>
          </Button>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search documents by name…"
            className="pl-9"
          />
        </div>
        <Select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as "all" | DocumentStatus)
          }
          className="sm:w-44"
        >
          <option value="all">All statuses</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="error">Error</option>
        </Select>
      </div>

      {loading ? (
        <ListSkeleton />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title={documents.length === 0 ? "No documents yet" : "No matching documents"}
          description={
            documents.length === 0
              ? "Upload a PDF, DOCX, TXT or CSV file to build your knowledge base."
              : "Try adjusting your search or filter."
          }
          action={
            documents.length === 0 ? (
              <Button asChild variant="outline" size="sm">
                <Link href="/upload">Upload documents</Link>
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Document</th>
                <th className="hidden px-4 py-3 font-medium sm:table-cell">Status</th>
                <th className="hidden px-4 py-3 font-medium md:table-cell">Chunks</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">Pages</th>
                <th className="hidden px-4 py-3 font-medium lg:table-cell">Size</th>
                <th className="hidden px-4 py-3 font-medium xl:table-cell">Uploaded</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((doc) => {
                const Icon = TYPE_ICONS[doc.file_type] ?? FileText;
                const busy = busyId === doc.id;
                return (
                  <tr key={doc.id} className="transition-colors hover:bg-secondary/30">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                          <Icon className="h-4 w-4" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium">{doc.name}</p>
                          <div className="mt-0.5 flex items-center gap-2 sm:hidden">
                            <DocumentStatusBadge status={doc.status} />
                          </div>
                          {doc.error && (
                            <p className="truncate text-xs text-destructive">
                              {doc.error}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 sm:table-cell">
                      <DocumentStatusBadge status={doc.status} />
                    </td>
                    <td className="hidden px-4 py-3 md:table-cell">
                      <Badge variant="secondary">
                        {formatNumber(doc.num_chunks)}
                      </Badge>
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">
                      {formatNumber(doc.num_pages)}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">
                      {formatBytes(doc.file_size)}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground xl:table-cell">
                      {formatDate(doc.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setPreviewId(doc.id)}
                          aria-label="Preview"
                          title="Preview"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={busy}
                          onClick={() => handleReprocess(doc)}
                          aria-label="Reprocess"
                          title="Reprocess"
                        >
                          <RefreshCw
                            className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"}
                          />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={busy}
                          onClick={() => setPendingDelete(doc)}
                          aria-label="Delete"
                          title="Delete"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <DocumentPreviewDialog
        open={previewId !== null}
        onOpenChange={(open) => !open && setPreviewId(null)}
        documentId={previewId}
        documentName={previewDoc?.name}
        totalChunks={previewDoc?.num_chunks}
      />

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete document"
        description="This permanently removes the document, its chunks and vector embeddings."
        className="max-w-md"
      >
        <p className="text-sm text-muted-foreground">
          Are you sure you want to delete{" "}
          <span className="font-medium text-foreground">{pendingDelete?.name}</span>?
          This action cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setPendingDelete(null)}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" onClick={confirmDelete}>
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
