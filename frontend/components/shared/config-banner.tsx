"use client";

import { AlertTriangle, Settings2 } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ConfigBannerProps {
  configured: boolean;
  online: boolean;
  className?: string;
}

/**
 * Shown when the backend is reachable but the OpenRouter key is missing, or
 * when the backend itself cannot be reached. Explains how to fix it.
 */
export function ConfigBanner({ configured, online, className }: ConfigBannerProps) {
  if (configured && online) return null;

  const offline = !online;

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="space-y-1 text-sm">
          <p className="font-medium">
            {offline
              ? "Cannot reach the RAGify AI backend"
              : "OPENROUTER_API_KEY is not configured"}
          </p>
          <p className="text-muted-foreground">
            {offline
              ? "Start the FastAPI server (uvicorn app.main:app --reload --port 8000) and make sure NEXT_PUBLIC_API_URL points to it."
              : "Chat answers cannot be generated until a key is provided. Copy .env.example to .env, set OPENROUTER_API_KEY, then restart the backend."}
          </p>
        </div>
      </div>
      {!offline && (
        <Button asChild variant="outline" size="sm">
          <Link href="/settings">
            <Settings2 className="h-3.5 w-3.5" />
            Configuration
          </Link>
        </Button>
      )}
    </div>
  );
}
