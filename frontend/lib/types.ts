export type DocumentStatus = "processing" | "ready" | "error";

export interface DocumentRecord {
  id: string;
  name: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  error?: string | null;
  num_chunks: number;
  num_pages: number;
  char_count: number;
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  accepted: DocumentRecord[];
  rejected: { filename: string; reason: string }[];
}

export interface ChunkRecord {
  id: string;
  chunk_index: number;
  page_number: number;
  content: string;
  token_estimate: number;
}

export interface Citation {
  index: number;
  document_id: string;
  document_name: string;
  page_number: number;
  chunk_index: number;
  similarity: number;
  label: string;
  excerpt: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number;
  content: string;
  score: number;
  similarity: number;
  rerank_score: number;
  char_start: number;
  char_end: number;
  chunk_index: number;
  source: string;
  citation: string;
}

export interface RetrievalStats {
  query: string;
  candidates: number;
  returned: number;
  threshold: number;
  top_k: number;
  top_score: number;
  avg_score: number;
  chunks?: RetrievedChunk[];
}

export interface RelevanceEvaluation {
  relevant: boolean;
  top_score: number;
  avg_score: number;
  chunk_count: number;
  reason: string;
}

export interface ClaimCheck {
  claim: string;
  supported: boolean;
  best_overlap: number;
  source: string;
}

export interface VerificationResult {
  verdict: "verified" | "partially_verified" | "unverified" | "no_sources";
  coverage: number;
  claims: ClaimCheck[];
  unsupported_claims: string[];
  disclaimer: string;
}

export interface ChatResult {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  contexts: RetrievedChunk[];
  retrieval: RetrievalStats;
  relevance: RelevanceEvaluation;
  verification: VerificationResult;
  analysis: Record<string, unknown>;
  status: string;
  errors: string[];
}

export interface MessageRecord {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  contexts: RetrievedChunk[];
  created_at: string;
}

export interface ConversationRecord {
  id: string;
  title: string;
  document_ids: string[];
  created_at: string;
  updated_at: string;
  message_count?: number;
  messages?: MessageRecord[];
}

export interface SettingsValues {
  openrouter_model: string;
  temperature: number;
  max_tokens: number;
  top_k: number;
  similarity_threshold: number;
  chunk_size: number;
  chunk_overlap: number;
  max_file_size_mb: number;
  embedding_model: string;
}

export interface SettingsResponse {
  values: SettingsValues;
  openrouter: { configured: boolean; model: string; base_url: string };
  embeddings: { model: string; loaded: boolean; dimension: number | null };
  vector_store: { backend: string; available: boolean; count?: number; path?: string; error?: string };
  uploads: { allowed_extensions: string[]; max_file_size_mb: number };
}

export interface StatsResponse {
  total_documents: number;
  ready_documents: number;
  total_chunks: number;
  total_conversations: number;
  total_questions: number;
  total_plans: number;
  ready_plans: number;
  recent_uploads: { id: string; name: string; status: string; num_chunks: number; created_at: string }[];
  recent_questions: { content: string; created_at: string; conversation_title: string }[];
  recent_plans: {
    id: string;
    title: string;
    business_name: string;
    status: string;
    section_count: number;
    word_count: number;
    created_at: string;
  }[];
  embeddings: { model: string; loaded: boolean; dimension: number | null };
  vector_store: { backend: string; available: boolean; count?: number; error?: string };
  openrouter: { configured: boolean; model: string };
}

export interface HealthResponse {
  status: string;
  app: string;
  openrouter_configured: boolean;
  model: string;
  embedding_model: string;
  embedding_loaded: boolean;
  vector_store: { backend?: string; available: boolean; count?: number };
}

export type StreamEventName =
  | "conversation"
  | "stage"
  | "token"
  | "error"
  | "done"
  | "result";

export interface StageEventData {
  name: string;
  status: "started" | "completed";
  detail?: Record<string, unknown>;
}

export interface StreamCallbacks {
  onConversation?: (data: { conversation_id: string; title: string }) => void;
  onStage?: (data: StageEventData) => void;
  onToken?: (text: string) => void;
  onError?: (data: { message: string; code?: string }) => void;
  onResult?: (data: ChatResult) => void;
  onDone?: () => void;
}

// ---------------------------------------------------------------------------
// Business plan generator
// ---------------------------------------------------------------------------
export type PlanStatus = "draft" | "generating" | "ready" | "error";

export interface PlanSectionRecord {
  id: string;
  key: string;
  title: string;
  position: number;
  content: string;
  citations: Citation[];
  word_count: number;
  status: string;
}

export interface PlanSummary {
  id: string;
  title: string;
  business_name: string;
  industry?: string | null;
  status: PlanStatus | string;
  overview: string;
  section_count: number;
  word_count: number;
  created_at: string;
  updated_at: string;
}

export interface PlanDetail extends PlanSummary {
  error?: string | null;
  inputs: Record<string, unknown>;
  document_ids: string[];
  model?: string | null;
  sections: PlanSectionRecord[];
}

export interface PlanCatalogSection {
  key: string;
  title: string;
  guidance: string;
  target_words: number;
  default: boolean;
}

export interface PlanSectionMeta {
  key: string;
  title: string;
  position: number;
}

export interface PlanGenerateInput {
  business_name: string;
  industry?: string;
  notes?: string;
  inputs?: Record<string, unknown>;
  document_ids?: string[];
  sections?: string[];
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface PlanHeaderEvent {
  plan_id: string;
  title: string;
  business_name: string;
  total: number;
  sections: PlanSectionMeta[];
}

export type PlanEventName =
  | "plan"
  | "stage"
  | "token"
  | "section"
  | "error"
  | "done"
  | "result";

export interface PlanStreamCallbacks {
  onPlan?: (data: PlanHeaderEvent) => void;
  onStage?: (data: StageEventData) => void;
  onToken?: (text: string, sectionKey?: string) => void;
  onSection?: (data: PlanSectionRecord) => void;
  onError?: (data: { message: string; code?: string }) => void;
  onResult?: (data: PlanDetail) => void;
  onDone?: () => void;
}
