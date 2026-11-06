"use client";

import {
  AlertTriangle,
  History,
  MessageSquarePlus,
  PanelRight,
  Send,
  Square,
  X,
} from "lucide-react";
import * as React from "react";

import { ContextPanel } from "@/components/chat/context-panel";
import { DocumentSelector } from "@/components/chat/document-selector";
import { MessageBubble } from "@/components/chat/message-bubble";
import { citationKey } from "@/components/chat/citation-chip";
import {
  WORKFLOW_STAGES,
  WorkflowStages,
  reduceStages,
} from "@/components/chat/workflow-stages";
import { ConfigBanner } from "@/components/shared/config-banner";
import { EmptyState, Spinner } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import {
  getConversation,
  getHealth,
  listConversations,
  listDocuments,
  streamChat,
  regenerateChat,
} from "@/lib/api";
import type {
  ChatResult,
  Citation,
  ConversationRecord,
  DocumentRecord,
  RelevanceEvaluation,
  RetrievedChunk,
  RetrievalStats,
  StageEventData,
  VerificationResult,
} from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  contexts?: RetrievedChunk[];
  verification?: VerificationResult | null;
  relevance?: RelevanceEvaluation | null;
  retrieval?: RetrievalStats | null;
  streaming?: boolean;
}

interface ChatViewProps {
  initialConversationId?: string | null;
  initialQuestion?: string | null;
}

function newId() {
  return Math.random().toString(36).slice(2);
}

export function ChatView({ initialConversationId, initialQuestion }: ChatViewProps) {
  const { toast } = useToast();

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = React.useState<string | null>(
    initialConversationId ?? null,
  );
  const [input, setInput] = React.useState(initialQuestion ?? "");
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [stageEvents, setStageEvents] = React.useState<StageEventData[]>([]);
  const [statusNote, setStatusNote] = React.useState<string | null>(null);

  const [documents, setDocuments] = React.useState<DocumentRecord[]>([]);
  const [selectedDocIds, setSelectedDocIds] = React.useState<string[]>([]);
  const [conversations, setConversations] = React.useState<ConversationRecord[]>([]);

  const [contexts, setContexts] = React.useState<RetrievedChunk[]>([]);
  const [verification, setVerification] = React.useState<VerificationResult | null>(null);
  const [relevance, setRelevance] = React.useState<RelevanceEvaluation | null>(null);
  const [retrieval, setRetrieval] = React.useState<RetrievalStats | null>(null);
  const [activeKey, setActiveKey] = React.useState<string | null>(null);

  const [showHistory, setShowHistory] = React.useState(false);
  const [showContext, setShowContext] = React.useState(false);
  const [online, setOnline] = React.useState(true);
  const [configured, setConfigured] = React.useState(true);
  const [loadingConversation, setLoadingConversation] = React.useState(false);

  const abortRef = React.useRef<AbortController | null>(null);
  const endRef = React.useRef<HTMLDivElement>(null);

  const stageStatuses = React.useMemo(
    () => reduceStages(stageEvents),
    [stageEvents],
  );

  const activeStage = React.useMemo(() => {
    for (let index = WORKFLOW_STAGES.length - 1; index >= 0; index -= 1) {
      const stage = WORKFLOW_STAGES[index];
      if (stageStatuses[stage.key] === "active") return stage.label;
    }
    return null;
  }, [stageStatuses]);

  const refreshSidebar = React.useCallback(async () => {
    try {
      const [docs, convs] = await Promise.all([
        listDocuments(),
        listConversations(),
      ]);
      setDocuments(docs);
      setConversations(convs);
    } catch (error) {
      toast({
        title: "Could not load workspace data",
        description: (error as Error).message,
        variant: "error",
      });
    }
  }, [toast]);

  const checkHealth = React.useCallback(async () => {
    try {
      const health = await getHealth();
      setOnline(health.status === "ok");
      setConfigured(health.openrouter_configured);
    } catch {
      setOnline(false);
    }
  }, []);

  React.useEffect(() => {
    refreshSidebar();
    checkHealth();
  }, [refreshSidebar, checkHealth]);

  const loadConversation = React.useCallback(
    async (id: string) => {
      setLoadingConversation(true);
      try {
        const conversation = await getConversation(id);
        setConversationId(conversation.id);
        setSelectedDocIds(conversation.document_ids ?? []);
        const loaded: ChatMessage[] = (conversation.messages ?? []).map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          citations: message.citations,
          contexts: message.contexts,
          verification: null,
        }));
        setMessages(loaded);
        const lastAssistant = [...loaded].reverse().find((m) => m.role === "assistant");
        setContexts(lastAssistant?.contexts ?? []);
        setVerification(lastAssistant?.verification ?? null);
        setActiveKey(null);
        setShowHistory(false);
      } catch (error) {
        toast({
          title: "Could not open conversation",
          description: (error as Error).message,
          variant: "error",
        });
      } finally {
        setLoadingConversation(false);
      }
    },
    [toast],
  );

  React.useEffect(() => {
    if (initialConversationId) {
      loadConversation(initialConversationId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stageEvents]);

  const startNewConversation = () => {
    if (isStreaming) return;
    setMessages([]);
    setConversationId(null);
    setStageEvents([]);
    setContexts([]);
    setVerification(null);
    setRelevance(null);
    setRetrieval(null);
    setActiveKey(null);
    setStatusNote(null);
    setShowHistory(false);
  };

  const runStream = React.useCallback(
    async (options: {
      question?: string;
      regenerate?: boolean;
      assistantId: string;
    }) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStageEvents([]);
      setStatusNote(null);
      setContexts([]);
      setVerification(null);
      setRelevance(null);
      setRetrieval(null);
      setActiveKey(null);

      const updateAssistant = (patch: Partial<ChatMessage>) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === options.assistantId ? { ...message, ...patch } : message,
          ),
        );
      };

      try {
        const callbacks = {
          onConversation: (data: { conversation_id: string; title: string }) => {
            setConversationId(data.conversation_id);
          },
          onStage: (data: StageEventData) => {
            setStageEvents((current) => [...current, data]);
          },
          onToken: (text: string) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === options.assistantId
                  ? { ...message, content: message.content + text }
                  : message,
              ),
            );
          },
          onError: (data: { message: string; code?: string }) => {
            setStatusNote(data.message);
            setMessages((current) =>
              current.map((message) =>
                message.id === options.assistantId
                  ? {
                      ...message,
                      content: `${message.content}\n\n> ⚠️ ${data.message}`.trim(),
                      streaming: false,
                    }
                  : message,
              ),
            );
          },
          onResult: (data: ChatResult) => {
            updateAssistant({
              content: data.answer || "",
              citations: data.citations,
              contexts: data.contexts,
              verification: data.verification,
              relevance: data.relevance,
              retrieval: data.retrieval,
              streaming: false,
            });
            setContexts(data.contexts ?? []);
            setVerification(data.verification ?? null);
            setRelevance(data.relevance ?? null);
            setRetrieval(data.retrieval ?? null);
            if ((data.answer ?? "").length > 0) {
              setShowContext(true);
            }
          },
          onDone: () => {
            updateAssistant({ streaming: false });
          },
        };

        if (options.regenerate && conversationId) {
          await regenerateChat(
            { conversation_id: conversationId },
            callbacks,
            controller.signal,
          );
        } else {
          await streamChat(
            {
              question: options.question ?? "",
              conversation_id: conversationId,
              document_ids: selectedDocIds.length ? selectedDocIds : undefined,
            },
            callbacks,
            controller.signal,
          );
        }
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          updateAssistant({ streaming: false });
        } else {
          const message = (error as Error).message;
          setStatusNote(message);
          updateAssistant({
            content: `> ⚠️ ${message}`,
            streaming: false,
          });
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
        refreshSidebar();
      }
    },
    [conversationId, selectedDocIds, refreshSidebar],
  );

  const send = async () => {
    const question = input.trim();
    if (!question || isStreaming) return;
    if (!configured) {
      toast({
        title: "OpenRouter is not configured",
        description:
          "Add OPENROUTER_API_KEY to your .env file and restart the backend.",
        variant: "error",
      });
      return;
    }

    const assistantId = newId();
    setMessages((current) => [
      ...current,
      { id: newId(), role: "user", content: question },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    await runStream({ question, assistantId });
  };

  const stop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  const regenerate = async () => {
    if (isStreaming || !conversationId) return;
    setMessages((current) => {
      const trimmed = [...current];
      if (trimmed.length && trimmed[trimmed.length - 1].role === "assistant") {
        trimmed.pop();
      }
      return trimmed;
    });
    const assistantId = newId();
    setMessages((current) => [
      ...current,
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);
    await runStream({ regenerate: true, assistantId });
  };

  const handleCitationSelect = (citation: Citation) => {
    setActiveKey(citationKey(citation));
    setShowContext(true);
  };

  const lastAssistantId = [...messages]
    .reverse()
    .find((message) => message.role === "assistant")?.id;

  const readyDocs = documents.filter((doc) => doc.status === "ready");

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-0 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Conversation history column */}
      {showHistory && (
        <div className="fixed inset-0 z-30 bg-navy-950/40 lg:hidden" onClick={() => setShowHistory(false)} />
      )}
      <aside
        className={cn(
          "w-64 shrink-0 flex-col border-r border-border bg-secondary/20",
          showHistory
            ? "fixed inset-y-0 left-0 z-40 flex lg:static lg:z-auto"
            : "hidden lg:flex",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-semibold">Conversations</span>
          <button
            onClick={() => setShowHistory(false)}
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary lg:hidden"
            aria-label="Close history"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">
              No conversations yet.
            </p>
          ) : (
            conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                onClick={() => loadConversation(conversation.id)}
                className={cn(
                  "w-full rounded-lg px-3 py-2 text-left transition-colors",
                  conversation.id === conversationId
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-secondary",
                )}
              >
                <p className="truncate text-sm font-medium">{conversation.title}</p>
                <p className="text-[11px] text-muted-foreground">
                  {conversation.message_count ?? 0} messages ·{" "}
                  {relativeTime(conversation.updated_at)}
                </p>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <Button variant="outline" size="sm" onClick={startNewConversation} disabled={isStreaming}>
            <MessageSquarePlus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">New chat</span>
          </Button>
          <DocumentSelector
            documents={documents}
            selected={selectedDocIds}
            onChange={setSelectedDocIds}
            disabled={isStreaming}
          />
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setShowHistory((value) => !value)}
              aria-label="Toggle conversations"
              className="lg:hidden"
            >
              <History className="h-4 w-4" />
            </Button>
            <Button
              variant={showContext ? "secondary" : "ghost"}
              size="icon"
              onClick={() => setShowContext((value) => !value)}
              aria-label="Toggle context panel"
            >
              <PanelRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
              <ConfigBanner configured={configured} online={online} className="mb-2" />

              {loadingConversation && (
                <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                  <Spinner className="mr-2" /> Loading conversation…
                </div>
              )}

              {!loadingConversation && messages.length === 0 && (
                <EmptyState
                  className="border-none"
                  icon={<MessageSquarePlus className="h-5 w-5" />}
                  title="Ask your documents anything"
                  description="RAGify AI retrieves the most relevant passages, generates an answer with OpenRouter and cites every source with page numbers."
                />
              )}

              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  role={message.role}
                  content={message.content}
                  citations={message.citations}
                  verification={message.verification}
                  streaming={message.streaming}
                  activeCitationKey={activeKey}
                  onCitationSelect={handleCitationSelect}
                  onRegenerate={message.id === lastAssistantId ? regenerate : undefined}
                  canRegenerate={!isStreaming}
                />
              ))}

              {isStreaming && (
                <div className="rounded-xl border border-border bg-secondary/20 p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                    <Spinner className="h-3.5 w-3.5" />
                    {activeStage ?? "Working on your question…"}
                  </div>
                  <WorkflowStages statuses={stageStatuses} />
                </div>
              )}

              <div ref={endRef} />
            </div>

            {statusNote && !isStreaming && (
              <div className="mx-4 mb-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-muted-foreground sm:mx-6">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                {statusNote}
              </div>
            )}

            <div className="border-t border-border p-3 sm:p-4">
              <div className="flex items-end gap-2">
                <Textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      send();
                    }
                  }}
                  placeholder="Ask a question about your documents…"
                  rows={2}
                  disabled={isStreaming}
                  className="max-h-40 min-h-[44px] resize-none"
                />
                {isStreaming ? (
                  <Button variant="destructive" size="lg" onClick={stop}>
                    <Square className="h-4 w-4" />
                    Stop
                  </Button>
                ) : (
                  <Button
                    variant="gradient"
                    size="lg"
                    onClick={send}
                    disabled={!input.trim()}
                  >
                    <Send className="h-4 w-4" />
                    Send
                  </Button>
                )}
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                {selectedDocIds.length
                  ? `Searching ${selectedDocIds.length} selected document${selectedDocIds.length === 1 ? "" : "s"}`
                  : `Searching all ${readyDocs.length} ready document${readyDocs.length === 1 ? "" : "s"}`}
                {" · "}
                Enter to send, Shift+Enter for a new line
              </p>
            </div>
          </div>

          {/* Context panel — inline on large screens */}
          {showContext && (
            <aside className="hidden w-[360px] shrink-0 border-l border-border lg:block">
              <ContextPanel
                contexts={contexts}
                verification={verification}
                relevance={relevance}
                retrieval={retrieval}
                activeKey={activeKey}
                className="h-full"
              />
            </aside>
          )}
        </div>
      </div>

      {/* Context panel — overlay on small screens */}
      {showContext && (
        <div className="fixed inset-0 z-40 flex justify-end bg-navy-950/40 lg:hidden">
          <div className="h-full w-full max-w-sm bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <Badge variant="secondary">Retrieved context</Badge>
              <button
                onClick={() => setShowContext(false)}
                className="rounded-md p-1 text-muted-foreground hover:bg-secondary"
                aria-label="Close context"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <ContextPanel
              contexts={contexts}
              verification={verification}
              relevance={relevance}
              retrieval={retrieval}
              activeKey={activeKey}
              className="h-[calc(100%-3.25rem)]"
            />
          </div>
        </div>
      )}
    </div>
  );
}
