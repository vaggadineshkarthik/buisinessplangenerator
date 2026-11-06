"use client";

import { Bot, Copy, RefreshCw, Sparkles, User } from "lucide-react";
import * as React from "react";

import { CitationChip, citationKey } from "@/components/chat/citation-chip";
import { Markdown } from "@/components/chat/markdown";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Citation, VerificationResult } from "@/lib/types";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  verification?: VerificationResult | null;
  streaming?: boolean;
  activeCitationKey?: string | null;
  onCitationSelect?: (citation: Citation) => void;
  onRegenerate?: () => void;
  canRegenerate?: boolean;
  extra?: React.ReactNode;
}

export function MessageBubble({
  role,
  content,
  citations = [],
  verification,
  streaming,
  activeCitationKey,
  onCitationSelect,
  onRegenerate,
  canRegenerate,
  extra,
}: MessageBubbleProps) {
  const [copied, setCopied] = React.useState(false);
  const isUser = role === "user";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const verdict = verification?.verdict;
  const showVerification =
    !isUser && verdict && verdict !== "no_sources" && verification;

  return (
    <div
      className={cn(
        "flex animate-fade-in gap-3",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <span
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white",
          isUser
            ? "bg-navy-700 dark:bg-navy-600"
            : "bg-gradient-to-br from-primary to-accent",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </span>

      <div className={cn("min-w-0 max-w-[85%] space-y-2", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-xl border px-4 py-3",
            isUser
              ? "border-border bg-secondary/60"
              : "border-border bg-card shadow-sm",
          )}
        >
          {content ? (
            isUser ? (
              <p className="whitespace-pre-wrap text-sm">{content}</p>
            ) : (
              <Markdown content={content} />
            )
          ) : (
            <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5 animate-pulse" />
              Thinking…
            </span>
          )}
          {streaming && content && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-blink rounded-sm bg-primary align-middle" />
          )}
        </div>

        {extra}

        {!isUser && showVerification && (
          <Badge
            variant={
              verdict === "verified"
                ? "success"
                : verdict === "partially_verified"
                  ? "warning"
                  : "danger"
            }
          >
            {verdict === "verified"
              ? "Verified against sources"
              : verdict === "partially_verified"
                ? "Partially verified"
                : "Not fully verified"}
          </Badge>
        )}

        {!isUser && citations.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Sources
            </p>
            <div className="flex flex-wrap gap-1.5">
              {citations.map((citation) => (
                <CitationChip
                  key={`${citation.index}-${citationKey(citation)}`}
                  citation={citation}
                  active={activeCitationKey === citationKey(citation)}
                  onClick={onCitationSelect}
                />
              ))}
            </div>
          </div>
        )}

        {!isUser && content && !streaming && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={copy}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Copy className="h-3 w-3" />
              {copied ? "Copied" : "Copy"}
            </button>
            {onRegenerate && canRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <RefreshCw className="h-3 w-3" />
                Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
