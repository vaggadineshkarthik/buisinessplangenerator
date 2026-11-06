"use client";

import { Check, ChevronDown, FileText, Library } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DocumentRecord } from "@/lib/types";

interface DocumentSelectorProps {
  documents: DocumentRecord[];
  selected: string[];
  onChange: (selected: string[]) => void;
  disabled?: boolean;
}

/** Scope a chat to a subset of documents (default: all ready documents). */
export function DocumentSelector({
  documents,
  selected,
  onChange,
  disabled,
}: DocumentSelectorProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const ready = documents.filter((doc) => doc.status === "ready");
  const label =
    selected.length === 0
      ? "All documents"
      : selected.length === 1
        ? ready.find((doc) => doc.id === selected[0])?.name ?? "1 document"
        : `${selected.length} documents`;

  const toggle = (id: string) => {
    onChange(
      selected.includes(id)
        ? selected.filter((value) => value !== id)
        : [...selected, id],
    );
  };

  return (
    <div className="relative" ref={ref}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        className="max-w-[220px] justify-between"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Library className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{label}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </Button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-2 w-72 animate-fade-in rounded-xl border border-border bg-popover p-2 shadow-xl">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              Search scope
            </span>
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-xs text-primary hover:underline"
            >
              Reset
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {ready.length === 0 ? (
              <p className="px-2 py-3 text-xs text-muted-foreground">
                No ready documents yet. Upload one to scope your search.
              </p>
            ) : (
              ready.map((doc) => {
                const checked = selected.includes(doc.id);
                return (
                  <button
                    key={doc.id}
                    type="button"
                    onClick={() => toggle(doc.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-secondary"
                  >
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        checked
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input",
                      )}
                    >
                      {checked && <Check className="h-3 w-3" />}
                    </span>
                    <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{doc.name}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
