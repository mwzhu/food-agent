import type {
  BrowserProfileSyncSession,
  BrowserProfileSyncStatus,
  ChatgptInstacartSmokeRunCreateRequest,
  CheckoutRunCreateRequest,
  FridgeItemCreate,
  FridgeItemRead,
  FridgeItemUpdate,
  InstacartSmokeRunCreateRequest,
  RunCreateRequest,
  RunRead,
  RunResumeRequest,
  RunTraceRead,
  UserProfileCreate,
  UserProfileRead,
  UserProfileUpdate,
  WalmartSmokeRunCreateRequest,
} from "@/lib/types";
import type {
  SupplementRunApproveRequest,
  SupplementRunCreateRequest,
  SupplementRunRead,
} from "@/lib/supplement-types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      detail = await response.text();
    }
    throw new ApiError(response.status, detail || "Request failed.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

export function createUser(payload: UserProfileCreate): Promise<UserProfileRead> {
  return request<UserProfileRead>("/v1/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getUser(userId: string): Promise<UserProfileRead> {
  return request<UserProfileRead>(`/v1/users/${userId}`);
}

export function updateUser(userId: string, payload: UserProfileUpdate): Promise<UserProfileRead> {
  return request<UserProfileRead>(`/v1/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listInventory(userId: string): Promise<FridgeItemRead[]> {
  return request<FridgeItemRead[]>(`/v1/users/${userId}/inventory`);
}

export function createInventoryItem(userId: string, payload: FridgeItemCreate): Promise<FridgeItemRead> {
  return request<FridgeItemRead>(`/v1/users/${userId}/inventory`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateInventoryItem(
  userId: string,
  itemId: number,
  payload: FridgeItemUpdate,
): Promise<FridgeItemRead> {
  return request<FridgeItemRead>(`/v1/users/${userId}/inventory/${itemId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteInventoryItem(userId: string, itemId: number): Promise<void> {
  await request<null>(`/v1/users/${userId}/inventory/${itemId}`, {
    method: "DELETE",
  });
}

export function listRuns(userId: string, limit = 10): Promise<RunRead[]> {
  const params = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
  });
  return request<RunRead[]>(`/v1/runs?${params.toString()}`);
}

export function createRun(payload: RunCreateRequest): Promise<RunRead> {
  return request<RunRead>("/v1/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: string): Promise<RunRead> {
  return request<RunRead>(`/v1/runs/${runId}`);
}

export function createSupplementRun(payload: SupplementRunCreateRequest): Promise<SupplementRunRead> {
  return request<SupplementRunRead>("/v1/supplements/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSupplementRun(runId: string): Promise<SupplementRunRead> {
  return request<SupplementRunRead>(`/v1/supplements/runs/${runId}`);
}

export function approveSupplementRun(
  runId: string,
  payload: SupplementRunApproveRequest,
): Promise<SupplementRunRead> {
  return request<SupplementRunRead>(`/v1/supplements/runs/${runId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createShoppingRun(runId: string): Promise<RunRead> {
  return request<RunRead>(`/v1/runs/${runId}/shopping`, {
    method: "POST",
  });
}

export function createCheckoutRun(runId: string, payload: CheckoutRunCreateRequest): Promise<RunRead> {
  return request<RunRead>(`/v1/runs/${runId}/checkout`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getWalmartProfileSyncStatus(): Promise<BrowserProfileSyncStatus> {
  return request<BrowserProfileSyncStatus>("/v1/checkout/walmart/profile-sync");
}

export function createWalmartProfileSyncSession(): Promise<BrowserProfileSyncSession> {
  return request<BrowserProfileSyncSession>("/v1/checkout/walmart/profile-sync/session", {
    method: "POST",
  });
}

export function createWalmartSmokeRun(payload: WalmartSmokeRunCreateRequest): Promise<RunRead> {
  return request<RunRead>("/v1/checkout/walmart/smoke-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getInstacartProfileSyncStatus(): Promise<BrowserProfileSyncStatus> {
  return request<BrowserProfileSyncStatus>("/v1/checkout/instacart/profile-sync");
}

export function createInstacartProfileSyncSession(): Promise<BrowserProfileSyncSession> {
  return request<BrowserProfileSyncSession>("/v1/checkout/instacart/profile-sync/session", {
    method: "POST",
  });
}

export function createInstacartSmokeRun(payload: InstacartSmokeRunCreateRequest): Promise<RunRead> {
  return request<RunRead>("/v1/checkout/instacart/smoke-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getChatgptProfileSyncStatus(): Promise<BrowserProfileSyncStatus> {
  return request<BrowserProfileSyncStatus>("/v1/checkout/chatgpt/profile-sync");
}

export function createChatgptProfileSyncSession(): Promise<BrowserProfileSyncSession> {
  return request<BrowserProfileSyncSession>("/v1/checkout/chatgpt/profile-sync/session", {
    method: "POST",
  });
}

export function createChatgptInstacartSmokeRun(payload: ChatgptInstacartSmokeRunCreateRequest): Promise<RunRead> {
  return request<RunRead>("/v1/checkout/chatgpt/instacart/smoke-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resumeRun(runId: string, payload: RunResumeRequest): Promise<RunRead> {
  return request<RunRead>(`/v1/runs/${runId}/resume`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRunTrace(runId: string): Promise<RunTraceRead> {
  return request<RunTraceRead>(`/v1/runs/${runId}/trace`);
}

export function getRunStreamUrl(runId: string): string {
  return `${API_BASE_URL}/v1/runs/${runId}/stream`;
}

export function getSupplementRunStreamUrl(runId: string): string {
  return `${API_BASE_URL}/v1/supplements/runs/${runId}/stream`;
}
