"use client";

import { BarChart3, FileText, Layers, MessagesSquare, TrendingUp } from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { CardGridSkeleton, ErrorState } from "@/components/shared/states";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getStats, listConversations, listDocuments } from "@/lib/api";
import type { ConversationRecord, DocumentRecord, StatsResponse } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

export default function AnalyticsPage() {
  const [stats, setStats] = React.useState<StatsResponse | null>(null);
  const [documents, setDocuments] = React.useState<DocumentRecord[]>([]);
  const [conversations, setConversations] = React.useState<ConversationRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, docs, convs] = await Promise.all([
        getStats(),
        listDocuments(),
        listConversations(),
      ]);
      setStats(statsData);
      setDocuments(docs);
      setConversations(convs);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const byType = React.useMemo(() => {
    const map = new Map<string, number>();
    documents.forEach((doc) => {
      map.set(doc.file_type, (map.get(doc.file_type) ?? 0) + 1);
    });
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [documents]);

  const byStatus = React.useMemo(() => {
    const map = new Map<string, number>();
    documents.forEach((doc) => {
      map.set(doc.status, (map.get(doc.status) ?? 0) + 1);
    });
    return ["ready", "processing", "error"].map((status) => ({
      status,
      count: map.get(status) ?? 0,
    }));
  }, [documents]);

  const topChunked = React.useMemo(
    () =>
      [...documents]
        .sort((a, b) => b.num_chunks - a.num_chunks)
        .slice(0, 6)
        .map((doc) => ({ name: doc.name, chunks: doc.num_chunks })),
    [documents],
  );

  const activity = React.useMemo(() => {
    const days = 14;
    const buckets = new Map<string, number>();
    const now = new Date();
    for (let i = days - 1; i >= 0; i -= 1) {
      const date = new Date(now);
      date.setDate(now.getDate() - i);
      buckets.set(date.toISOString().slice(0, 10), 0);
    }
    conversations.forEach((conversation) => {
      const key = new Date(conversation.created_at).toISOString().slice(0, 10);
      if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1);
    });
    return Array.from(buckets.entries()).map(([date, count]) => ({ date, count }));
  }, [conversations]);

  const maxActivity = Math.max(1, ...activity.map((point) => point.count));
  const maxChunks = Math.max(1, ...topChunked.map((item) => item.chunks));
  const totalDocs = Math.max(1, documents.length);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Analytics"
        description="Understand how your knowledge base and conversations are growing."
      />

      {loading ? (
        <CardGridSkeleton />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : stats ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Documents"
              value={formatNumber(stats.total_documents)}
              hint={`${formatNumber(stats.ready_documents)} ready`}
              icon={<FileText className="h-5 w-5" />}
            />
            <StatCard
              label="Chunks embedded"
              value={formatNumber(stats.total_chunks)}
              hint={`${formatNumber(stats.vector_store.count ?? 0)} vectors stored`}
              icon={<Layers className="h-5 w-5" />}
              accent="accent"
            />
            <StatCard
              label="Conversations"
              value={formatNumber(stats.total_conversations)}
              icon={<MessagesSquare className="h-5 w-5" />}
              accent="emerald"
            />
            <StatCard
              label="Questions asked"
              value={formatNumber(stats.total_questions)}
              icon={<TrendingUp className="h-5 w-5" />}
              accent="amber"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Conversation activity</CardTitle>
                <CardDescription>New conversations over the last 14 days</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex h-40 items-end gap-1.5">
                  {activity.map((point) => (
                    <div
                      key={point.date}
                      className="group relative flex flex-1 flex-col items-center justify-end"
                      title={`${point.date}: ${point.count}`}
                    >
                      <div
                        className="w-full rounded-t bg-gradient-to-t from-primary/60 to-accent/80 transition-all group-hover:from-primary group-hover:to-accent"
                        style={{
                          height: `${Math.max(4, (point.count / maxActivity) * 100)}%`,
                        }}
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                  <span>{activity[0]?.date}</span>
                  <span>{activity[activity.length - 1]?.date}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Documents by type</CardTitle>
                <CardDescription>Distribution across file formats</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {byType.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No documents yet.</p>
                ) : (
                  byType.map(([type, count]) => (
                    <div key={type} className="space-y-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium uppercase">{type}</span>
                        <span className="text-muted-foreground">{count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                          style={{ width: `${(count / totalDocs) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Processing status</CardTitle>
                <CardDescription>Where each document stands</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {byStatus.map((item) => (
                  <div key={item.status} className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="capitalize font-medium">{item.status}</span>
                      <span className="text-muted-foreground">{item.count}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className={`h-full rounded-full ${
                          item.status === "ready"
                            ? "bg-emerald-500"
                            : item.status === "processing"
                              ? "bg-amber-500"
                              : "bg-destructive"
                        }`}
                        style={{ width: `${(item.count / totalDocs) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Most chunked documents</CardTitle>
                <CardDescription>Top documents by indexed chunks</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {topChunked.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No documents yet.</p>
                ) : (
                  topChunked.map((item) => (
                    <div key={item.name} className="space-y-1.5">
                      <div className="flex items-center justify-between gap-2 text-sm">
                        <span className="truncate font-medium">{item.name}</span>
                        <span className="shrink-0 text-muted-foreground">
                          {formatNumber(item.chunks)}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-accent to-primary"
                          style={{ width: `${(item.chunks / maxChunks) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <BarChart3 className="h-4 w-4" /> No analytics available yet.
        </div>
      )}
    </div>
  );
}
