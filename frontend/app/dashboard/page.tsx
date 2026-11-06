"use client";

import {
  ArrowUpRight,
  Briefcase,
  Cpu,
  Database,
  FileText,
  Layers,
  MessageSquare,
  MessagesSquare,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { PageHeader } from "@/components/shared/page-header";
import { ConfigBanner } from "@/components/shared/config-banner";
import { StatCard } from "@/components/shared/stat-card";
import { DocumentStatusBadge } from "@/components/shared/document-status-badge";
import { CardGridSkeleton, EmptyState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getHealth, getStats } from "@/lib/api";
import type { HealthResponse, StatsResponse } from "@/lib/types";
import { formatNumber, relativeTime, truncate } from "@/lib/utils";

export default function DashboardPage() {
  const [stats, setStats] = React.useState<StatsResponse | null>(null);
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, healthData] = await Promise.all([getStats(), getHealth()]);
      setStats(statsData);
      setHealth(healthData);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Overview"
        description="A snapshot of your business plans, knowledge base, conversations and model status."
        actions={
          <Button asChild variant="gradient" size="sm">
            <Link href="/plan">
              <Briefcase className="h-4 w-4" />
              Generate a plan
            </Link>
          </Button>
        }
      />

      <ConfigBanner
        online={health?.status === "ok"}
        configured={health?.openrouter_configured ?? false}
      />

      {error && !loading && (
        <ErrorState message={error} onRetry={load} />
      )}

      {loading && <CardGridSkeleton />}

      {!loading && stats && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard
              label="Business plans"
              value={formatNumber(stats.total_plans)}
              hint={`${formatNumber(stats.ready_plans)} ready`}
              icon={<Briefcase className="h-5 w-5" />}
              accent="primary"
            />
            <StatCard
              label="Documents"
              value={formatNumber(stats.total_documents)}
              hint={`${formatNumber(stats.ready_documents)} ready`}
              icon={<FileText className="h-5 w-5" />}
              accent="primary"
            />
            <StatCard
              label="Chunks"
              value={formatNumber(stats.total_chunks)}
              hint="Indexed vector chunks"
              icon={<Layers className="h-5 w-5" />}
              accent="accent"
            />
            <StatCard
              label="Conversations"
              value={formatNumber(stats.total_conversations)}
              hint="Active threads"
              icon={<MessagesSquare className="h-5 w-5" />}
              accent="emerald"
            />
            <StatCard
              label="Questions"
              value={formatNumber(stats.total_questions)}
              hint="Asked by you"
              icon={<MessageSquare className="h-5 w-5" />}
              accent="amber"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle>Recent uploads</CardTitle>
                  <CardDescription>The latest documents added</CardDescription>
                </div>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/documents">
                    View all
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              </CardHeader>
              <CardContent>
                {stats.recent_uploads.length === 0 ? (
                  <EmptyState
                    icon={<UploadCloud className="h-5 w-5" />}
                    title="No documents yet"
                    description="Upload a PDF, DOCX, TXT or CSV file to start building your knowledge base."
                    action={
                      <Button asChild size="sm" variant="outline">
                        <Link href="/upload">Upload documents</Link>
                      </Button>
                    }
                  />
                ) : (
                  <ul className="divide-y divide-border">
                    {stats.recent_uploads.map((doc) => (
                      <li
                        key={doc.id}
                        className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{doc.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {formatNumber(doc.num_chunks)} chunks ·{" "}
                            {relativeTime(doc.created_at)}
                          </p>
                        </div>
                        <DocumentStatusBadge
                          status={doc.status as never}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>System status</CardTitle>
                <CardDescription>Model &amp; storage health</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <StatusRow
                  icon={<Cpu className="h-4 w-4" />}
                  label="OpenRouter"
                  value={stats.openrouter.configured ? "Configured" : "Missing key"}
                  ok={stats.openrouter.configured}
                  hint={stats.openrouter.model}
                />
                <StatusRow
                  icon={<Sparkles className="h-4 w-4" />}
                  label="Embedding model"
                  value={
                    stats.embeddings.loaded
                      ? "Loaded"
                      : stats.embeddings.dimension
                        ? "Cached"
                        : "Idle"
                  }
                  ok
                  hint={stats.embeddings.model}
                />
                <StatusRow
                  icon={<Database className="h-4 w-4" />}
                  label="Vector store"
                  value={stats.vector_store.available ? "Available" : "Unavailable"}
                  ok={stats.vector_store.available}
                  hint={
                    stats.vector_store.count !== undefined
                      ? `${formatNumber(stats.vector_store.count)} vectors · ${stats.vector_store.backend}`
                      : stats.vector_store.backend
                  }
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent questions</CardTitle>
              <CardDescription>Your latest prompts across conversations</CardDescription>
            </CardHeader>
            <CardContent>
              {stats.recent_questions.length === 0 ? (
                <EmptyState
                  icon={<MessageSquare className="h-5 w-5" />}
                  title="No questions asked yet"
                  description="Head to the AI Chat and ask something about your documents."
                  action={
                    <Button asChild size="sm" variant="outline">
                      <Link href="/chat">Open AI Chat</Link>
                    </Button>
                  }
                />
              ) : (
                <ul className="divide-y divide-border">
                  {stats.recent_questions.map((question, index) => (
                    <li key={index} className="py-3 first:pt-0 last:pb-0">
                      <p className="text-sm">{truncate(question.content, 160)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {question.conversation_title} ·{" "}
                        {relativeTime(question.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function StatusRow({
  icon,
  label,
  value,
  hint,
  ok,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
  ok: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">{label}</p>
          <Badge variant={ok ? "success" : "warning"}>{value}</Badge>
        </div>
        {hint && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p>
        )}
      </div>
    </div>
  );
}
