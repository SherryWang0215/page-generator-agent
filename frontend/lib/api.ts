import type {
  GeneratePageRequest,
  GeneratePageResponse,
  RevisePageRequest,
  StoredPageResponse,
} from "./pageDsl";

// -- Conversation types --

export interface ConversationItem {
  conversation_id: string;
  user_id: string;
  page_id: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
  status: string;
}

export interface ConversationListResponse {
  conversations: ConversationItem[];
  total: number;
}

export interface MessageItem {
  message_id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface SendMessageResponse {
  message_id: string;
  content: string;
  page_id: string | null;
  pages: Record<string, unknown>[];
  request_id?: string | null;
  status?: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED" | null;
  celery_task_id?: string | null;
  intent?: "generate" | "revise" | "chat" | null;
}

export interface ProfileData {
  user_id: string;
  preferences: Record<string, unknown>;
  extracted_at: string | null;
  source_conversation_ids: string[];
}

export interface SearchResultItem {
  conversation_id: string;
  title: string | null;
  score: number;
  highlights: string[];
  page_id: string | null;
  message_count: number;
  last_message_at: string | null;
}

export interface SearchResponse {
  results: SearchResultItem[];
  total: number;
}

// -- Helpers --

function getUserId(): string {
  let userId = localStorage.getItem("pg_user_id");
  if (!userId) {
    userId = crypto.randomUUID();
    localStorage.setItem("pg_user_id", userId);
  }
  return userId;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    if (!payload?.detail) {
      throw new Error("request failed");
    }
    // FastAPI validation errors return detail as an array of {loc, msg, type}
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.map((d: { msg?: string }) => d.msg ?? String(d));
      throw new Error(messages.join("; "));
    }
    throw new Error(String(payload.detail));
  }
  return (await response.json()) as T;
}

// -- Page APIs --

export async function generatePage(payload: GeneratePageRequest): Promise<GeneratePageResponse> {
  const response = await fetch("/api/agent/page/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return handleResponse<GeneratePageResponse>(response);
}

export async function fetchGenerationResult(requestId: string): Promise<GeneratePageResponse> {
  const response = await fetch(`/api/agent/page/result?request_id=${encodeURIComponent(requestId)}`);
  return handleResponse<GeneratePageResponse>(response);
}

export async function waitForGenerationResult(
  requestId: string,
  onStatus?: (status: GeneratePageResponse["status"]) => void,
): Promise<GeneratePageResponse> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const result = await fetchGenerationResult(requestId);
    onStatus?.(result.status);

    if (result.status === "SUCCESS") {
      return result;
    }
    if (result.status === "FAILED" || result.status === "CANCELLED") {
      throw new Error(result.error_message ?? `任务${result.status}`);
    }

    await delay(1000);
  }

  throw new Error("生成任务超时，请稍后在结果接口中查询");
}

export async function fetchPage(pageId: string): Promise<StoredPageResponse> {
  const response = await fetch(`/api/pages/${pageId}`);
  return handleResponse<StoredPageResponse>(response);
}

export async function revisePage(payload: RevisePageRequest): Promise<GeneratePageResponse> {
  const response = await fetch("/api/agent/page/revise", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return handleResponse<GeneratePageResponse>(response);
}

// -- Conversation APIs --

export async function createConversation(pageId?: string): Promise<ConversationItem> {
  const response = await fetch("/api/conversations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-ID": getUserId(),
    },
    body: JSON.stringify({ page_id: pageId ?? null }),
  });
  return handleResponse<ConversationItem>(response);
}

export async function listConversations(limit = 20, offset = 0): Promise<ConversationListResponse> {
  const response = await fetch(`/api/conversations?limit=${limit}&offset=${offset}`, {
    headers: { "X-User-ID": getUserId() },
  });
  return handleResponse<ConversationListResponse>(response);
}

export async function getConversation(conversationId: string) {
  const response = await fetch(`/api/conversations/${conversationId}`);
  return handleResponse<{ conversation: ConversationItem; messages: MessageItem[] }>(response);
}

export async function archiveConversation(conversationId: string): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
    headers: { "X-User-ID": getUserId() },
  });
  return handleResponse(response);
}

export async function sendMessage(
  conversationId: string,
  content: string,
): Promise<SendMessageResponse> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-ID": getUserId(),
    },
    body: JSON.stringify({ content }),
  });
  return handleResponse<SendMessageResponse>(response);
}

export async function listMessages(
  conversationId: string,
  limit = 50,
  offset = 0,
): Promise<{ messages: MessageItem[]; total: number }> {
  const response = await fetch(
    `/api/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`,
  );
  return handleResponse<{ messages: MessageItem[]; total: number }>(response);
}

// -- Profile APIs --

export async function getProfile(): Promise<ProfileData> {
  const response = await fetch(`/api/profile/${getUserId()}`);
  return handleResponse<ProfileData>(response);
}

export async function extractProfile(): Promise<ProfileData> {
  const response = await fetch(`/api/profile/${getUserId()}/extract`, { method: "POST" });
  return handleResponse<ProfileData>(response);
}

// -- Search API --

export async function searchConversations(query: string, limit = 10): Promise<SearchResponse> {
  const response = await fetch(
    `/api/conversations/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    { headers: { "X-User-ID": getUserId() } },
  );
  return handleResponse<SearchResponse>(response);
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
