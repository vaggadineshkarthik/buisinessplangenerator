"use client";

import { MessagesSquare, MessageSquarePlus, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, ListSkeleton, Spinner } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { deleteConversation, getConversation, listConversations } from "@/lib/api";
import type { ConversationRecord } from "@/lib/types";
import { formatDate, relativeTime, truncate } from "@/lib/utils";

export default function HistoryPage() {
  const { toast } = useToast();
  const [conversations, setConversations] = React.useState<ConversationRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [pendingDelete, setPendingDelete] =
    React.useState<ConversationRecord | null>(null);
  const [preview, setPreview] = React.useState<ConversationRecord | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setConversations(await listConversations());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const openPreview = async (conversation: ConversationRecord) => {
    setPreviewLoading(true);
    setPreview({ ...conversation, messages: [] });
    try {
      const full = await getConversation(conversation.id);
      setPreview(full);
    } catch (err) {
      toast({
        title: "Could not load conversation",
        description: (err as Error).message,
        variant: "error",
      });
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteConversation(target.id);
      setConversations((current) => current.filter((item) => item.id !== target.id));
      toast({ title: "Conversation deleted", variant: "success" });
    } catch (err) {
      toast({
        title: "Delete failed",
        description: (err as Error).message,
        variant: "error",
      });
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Conversations"
        description="Review and manage your past question threads."
        actions={
          <Button asChild variant="gradient" size="sm">
            <Link href="/chat">
              <MessageSquarePlus className="h-4 w-4" />
              New chat
            </Link>
          </Button>
        }
      />

      {loading ? (
        <ListSkeleton />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : conversations.length === 0 ? (
        <EmptyState
          icon={<MessagesSquare className="h-5 w-5" />}
          title="No conversations yet"
          description="Start a chat and your conversation history will appear here."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/chat">Open AI Chat</Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {conversations.map((conversation) => (
            <Card key={conversation.id} className="card-hover">
              <CardContent className="flex items-center gap-4 pt-6">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-accent/15 text-primary">
                  <MessagesSquare className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{conversation.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {conversation.message_count ?? 0} messages ·{" "}
                    {conversation.document_ids?.length
                      ? `${conversation.document_ids.length} documents scoped`
                      : "all documents"}{" "}
                    · {relativeTime(conversation.updated_at)}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={() => openPreview(conversation)}>
                    Preview
                  </Button>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/chat?conversation=${conversation.id}`}>Open</Link>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setPendingDelete(conversation)}
                    aria-label="Delete conversation"
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={preview !== null}
        onOpenChange={(open) => !open && setPreview(null)}
        title={preview?.title ?? "Conversation"}
        description={
          preview ? `Created ${formatDate(preview.created_at)}` : undefined
        }
      >
        {previewLoading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Spinner /> Loading messages…
          </div>
        ) : (
          <ul className="space-y-3">
            {(preview?.messages ?? []).map((message) => (
              <li
                key={message.id}
                className="rounded-lg border border-border bg-secondary/20 p-3"
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant={message.role === "user" ? "secondary" : "default"}>
                    {message.role === "user" ? "You" : "RAGify AI"}
                  </Badge>
                  <span className="text-[11px] text-muted-foreground">
                    {relativeTime(message.created_at)}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {truncate(message.content, 600)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Dialog>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete conversation"
        description="This permanently removes the conversation and its messages."
        className="max-w-md"
      >
        <p className="text-sm text-muted-foreground">
          Delete{" "}
          <span className="font-medium text-foreground">{pendingDelete?.title}</span>?
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
