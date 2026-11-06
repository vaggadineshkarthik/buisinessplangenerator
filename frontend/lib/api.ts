import type {
  ChatResult,
  ChunkRecord,
  ConversationRecord,
  DocumentRecord,
  HealthResponse,
  PlanCatalogSection,
  PlanDetail,
  PlanGenerateInput,
  PlanSectionRecord,
  PlanStreamCallbacks,
  PlanSummary,
  SettingsResponse,
  SettingsValues,
  StatsResponse,
  StreamCallbacks,
  UploadResult,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Cannot reach the RAGify AI backend at ${API_BASE_URL}. Make sure the FastAPI server is running.`,
      0,
    );
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        message = payload.detail;
      } else if (payload?.detail?.message) {
        message = payload.detail.message;
      } else if (payload?.detail) {
        message = JSON.stringify(payload.detail);
      } else if (payload?.error) {
        message = payload.error;
      }
    } catch {
      /* keep default message */
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------
export const getHealth = () => request<HealthResponse>("/health");
export const getStats = () => request<StatsResponse>("/api/stats");

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
export const listDocuments = () => request<DocumentRecord[]>("/api/documents");

export const getDocument = (id: string) =>
  request<DocumentRecord>(`/api/documents/${id}`);

export const getDocumentChunks = (id: string, limit = 50, offset = 0) =>
  request<{ document_id: string; total_chunks: number; chunks: ChunkRecord[] }>(
    `/api/documents/${id}/chunks?limit=${limit}&offset=${offset}`,
  );

export function uploadDocuments(
  files: File[],
  options: { processInline?: boolean; onProgress?: (percent: number) => void } = {},
): Promise<UploadResult> {
  const { processInline = false, onProgress } = options;
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const path = `/api/documents/upload${processInline ? "?process_inline=true" : ""}`;

  // Use XHR so we can report real upload progress.
  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as UploadResult);
      } else {
        const detail = (payload as { detail?: unknown })?.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail)
              : `Upload failed with status ${xhr.status}`;
        reject(new ApiError(message, xhr.status));
      }
    };
    xhr.onerror = () =>
      reject(new ApiError("Network error while uploading documents.", 0));
    xhr.send(form);
  });
}

export const deleteDocument = (id: string) =>
  request<{ deleted: boolean }>(`/api/documents/${id}`, { method: "DELETE" });

export const reprocessDocument = (id: string) =>
  request<DocumentRecord>(`/api/documents/${id}/reprocess`, { method: "POST" });

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
export interface ChatPayload {
  question: string;
  conversation_id?: string | null;
  document_ids?: string[];
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export const sendChat = (payload: ChatPayload) =>
  request<ChatResult>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const searchKnowledgeBase = (payload: {
  query: string;
  document_ids?: string[];
  top_k?: number;
  similarity_threshold?: number;
}) =>
  request<import("./types").RetrievalStats>("/api/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });

/**
 * Streams a chat response using fetch + Server-Sent Events.
 * Returns a promise that resolves once the stream is fully consumed.
 */
export async function streamChat(
  payload: ChatPayload,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  endpoint = "/api/chat/stream",
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      `Cannot reach the RAGify AI backend at ${API_BASE_URL}.`,
      0,
    );
  }

  if (!response.ok || !response.body) {
    let message = `Streaming failed with status ${response.status}`;
    if (response.status === 404) message = "Conversation not found.";
    if (response.status === 503) {
      message =
        "OPENROUTER_API_KEY is not configured. Add it to your .env file and restart the backend.";
    }
    throw new ApiError(message, response.status);
  }

  const reader = response.body.getReader();
  await consumeSse(reader, (eventName, data) =>
    dispatchEvent(eventName, data, callbacks),
  );
}

async function consumeSse(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      if (!frame.trim()) continue;
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (!dataLines.length) continue;
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataLines.join("\n"));
      } catch {
        continue;
      }
      onEvent(eventName, data);
    }
  }
}

function dispatchEvent(
  eventName: string,
  data: Record<string, unknown>,
  callbacks: StreamCallbacks,
) {
  switch (eventName) {
    case "conversation":
      callbacks.onConversation?.(data as { conversation_id: string; title: string });
      break;
    case "stage":
      callbacks.onStage?.(data as never);
      break;
    case "token":
      callbacks.onToken?.((data.text as string) ?? "");
      break;
    case "error":
      callbacks.onError?.(data as { message: string; code?: string });
      break;
    case "result":
      callbacks.onResult?.(data as unknown as ChatResult);
      break;
    case "done":
      callbacks.onDone?.();
      break;
    default:
      break;
  }
}

export const regenerateChat = (
  payload: { conversation_id: string; model?: string; temperature?: number },
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
) => streamChat(payload as ChatPayload, callbacks, signal, "/api/chat/regenerate");

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------
export const listConversations = () =>
  request<ConversationRecord[]>("/api/conversations");

export const getConversation = (id: string) =>
  request<ConversationRecord>(`/api/conversations/${id}`);

export const createConversation = (payload: { title?: string; document_ids?: string[] }) =>
  request<ConversationRecord>("/api/conversations", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteConversation = (id: string) =>
  request<{ deleted: boolean }>(`/api/conversations/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Business plan generator
// ---------------------------------------------------------------------------
export const getPlanCatalog = () =>
  request<{ sections: PlanCatalogSection[] }>("/api/plans/catalog");

export const listPlans = () => request<PlanSummary[]>("/api/plans");

export const getPlan = (id: string) => request<PlanDetail>(`/api/plans/${id}`);

export const generatePlan = (payload: PlanGenerateInput) =>
  request<PlanDetail>("/api/plans/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deletePlan = (id: string) =>
  request<{ deleted: boolean; plan_id: string }>(`/api/plans/${id}`, {
    method: "DELETE",
  });

export const planExportUrl = (
  id: string,
  format: "markdown" | "text" = "markdown",
) => `${API_BASE_URL}/api/plans/${id}/export?format=${format}`;

async function streamPlanEndpoint(
  path: string,
  body: Record<string, unknown>,
  callbacks: PlanStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      `Cannot reach the RAGify AI backend at ${API_BASE_URL}.`,
      0,
    );
  }

  if (!response.ok || !response.body) {
    let message = `Plan generation failed with status ${response.status}`;
    if (response.status === 404) message = "Plan not found.";
    if (response.status === 503) {
      message =
        "OPENROUTER_API_KEY is not configured. Add it to your .env file and restart the backend.";
    }
    throw new ApiError(message, response.status);
  }

  await consumeSse(response.body.getReader(), (eventName, data) => {
    switch (eventName) {
      case "plan":
        callbacks.onPlan?.(data as unknown as import("./types").PlanHeaderEvent);
        break;
      case "stage":
        callbacks.onStage?.(data as never);
        break;
      case "token":
        callbacks.onToken?.(
          (data.text as string) ?? "",
          (data.section_key as string) ?? undefined,
        );
        break;
      case "section":
        callbacks.onSection?.(data as unknown as PlanSectionRecord);
        break;
      case "error":
        callbacks.onError?.(data as { message: string; code?: string });
        break;
      case "result":
        callbacks.onResult?.(data as unknown as PlanDetail);
        break;
      case "done":
        callbacks.onDone?.();
        break;
      default:
        break;
    }
  });
}

/** Streams a full business plan. Emits `plan`, `stage`, `token`, `section`,
 *  `error`, `done` and `result` events exactly as the backend produces them. */
export const streamPlan = (
  payload: PlanGenerateInput,
  callbacks: PlanStreamCallbacks,
  signal?: AbortSignal,
) =>
  streamPlanEndpoint(
    "/api/plans/generate/stream",
    payload as unknown as Record<string, unknown>,
    callbacks,
    signal,
  );

/** Re-runs an existing plan, streaming a fresh set of sections. */
export const regeneratePlan = (
  planId: string,
  callbacks: PlanStreamCallbacks,
  signal?: AbortSignal,
) =>
  streamPlanEndpoint(
    `/api/plans/${planId}/regenerate`,
    {},
    callbacks,
    signal,
  );

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
export const getSettings = () => request<SettingsResponse>("/api/settings");

export const updateSettings = (payload: Partial<SettingsValues>) =>
  request<{ updated: boolean; values: SettingsValues }>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });

export const getModels = () =>
  request<{ models: { id: string; name: string; context_length?: number }[] }>(
    "/api/settings/models",
  );

export const getDiagnostics = () =>
  request<Record<string, unknown>>("/api/settings/diagnostics");

export { ApiError };
