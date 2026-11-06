"use client";

import {
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  FileType,
  FileType2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { uploadDocuments } from "@/lib/api";
import type { UploadResult } from "@/lib/types";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPTED = [".pdf", ".docx", ".txt", ".csv"];

const TYPE_ICONS: Record<string, typeof FileText> = {
  "application/pdf": FileText,
  "text/plain": FileType,
  "text/csv": FileSpreadsheet,
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType2,
};

function iconFor(file: File) {
  return TYPE_ICONS[file.type] ?? FileText;
}

function isAccepted(file: File) {
  const lower = file.name.toLowerCase();
  return ACCEPTED.some((ext) => lower.endsWith(ext));
}

export default function UploadPage() {
  const { toast } = useToast();
  const [files, setFiles] = React.useState<File[]>([]);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [results, setResults] = React.useState<UploadResult | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const next = Array.from(incoming);
    setFiles((current) => {
      const seen = new Set(current.map((file) => `${file.name}:${file.size}`));
      const merged = [...current];
      for (const file of next) {
        const key = `${file.name}:${file.size}`;
        if (!seen.has(key)) {
          merged.push(file);
          seen.add(key);
        }
      }
      return merged;
    });
  };

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files);
  };

  const removeFile = (index: number) =>
    setFiles((current) => current.filter((_, i) => i !== index));

  const startUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    setProgress(0);
    setResults(null);
    try {
      const result = await uploadDocuments(files, {
        onProgress: setProgress,
      });
      setResults(result);
      setFiles([]);
      const accepted = result.accepted.length;
      const rejected = result.rejected.length;
      toast({
        title: `${accepted} document${accepted === 1 ? "" : "s"} uploaded`,
        description: rejected
          ? `${rejected} file${rejected === 1 ? "" : "s"} skipped.`
          : "Processing and embedding started in the background.",
        variant: accepted ? "success" : "error",
      });
    } catch (error) {
      toast({
        title: "Upload failed",
        description: (error as Error).message,
        variant: "error",
      });
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Upload Documents"
        description="Add PDF, DOCX, TXT or CSV files. They will be extracted, chunked and embedded automatically."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/documents">Knowledge base</Link>
          </Button>
        }
      />

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-secondary/30",
        )}
      >
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-white">
          <UploadCloud className="h-6 w-6" />
        </span>
        <div className="space-y-1">
          <p className="font-medium">
            {dragging ? "Drop files to add them" : "Drag & drop files here"}
          </p>
          <p className="text-sm text-muted-foreground">
            or click to browse · {ACCEPTED.join(", ")} · up to 25 MB each
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED.join(",")}
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-medium">
                {files.length} file{files.length === 1 ? "" : "s"} ready
              </p>
              <button
                onClick={() => setFiles([])}
                className="text-xs text-muted-foreground hover:text-foreground"
                disabled={uploading}
              >
                Clear all
              </button>
            </div>
            <ul className="space-y-2">
              {files.map((file, index) => {
                const Icon = iconFor(file);
                const accepted = isAccepted(file);
                return (
                  <li
                    key={`${file.name}-${index}`}
                    className="flex items-center gap-3 rounded-lg border border-border bg-secondary/20 p-3"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatBytes(file.size)}
                      </p>
                    </div>
                    {!accepted && <Badge variant="danger">Unsupported</Badge>}
                    <button
                      onClick={() => removeFile(index)}
                      disabled={uploading}
                      className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-40"
                      aria-label="Remove file"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                );
              })}
            </ul>

            {uploading && (
              <div className="mt-4 space-y-2">
                <Progress value={progress} />
                <p className="text-center text-xs text-muted-foreground">
                  Uploading… {progress}%
                </p>
              </div>
            )}

            <div className="mt-4 flex justify-end">
              <Button
                variant="gradient"
                onClick={startUpload}
                disabled={uploading || files.length === 0}
              >
                {uploading ? <Spinner /> : <UploadCloud className="h-4 w-4" />}
                {uploading ? "Uploading…" : "Upload & process"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {results && (
        <div className="grid gap-4 sm:grid-cols-2">
          {results.accepted.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-4 w-4" />
                  Accepted ({results.accepted.length})
                </div>
                <ul className="space-y-2">
                  {results.accepted.map((doc) => (
                    <li key={doc.id} className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm">{doc.name}</span>
                      <Badge variant="secondary">{doc.status}</Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          {results.rejected.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-destructive">
                  <XCircle className="h-4 w-4" />
                  Skipped ({results.rejected.length})
                </div>
                <ul className="space-y-2">
                  {results.rejected.map((item) => (
                    <li key={item.filename} className="text-sm">
                      <p className="truncate font-medium">{item.filename}</p>
                      <p className="text-xs text-muted-foreground">{item.reason}</p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
