import type {
  FridgeItemCreate,
  FridgeItemRead,
  FridgeItemUpdate,
  RunCreateRequest,
  RunRead,
  RunTraceRead,
  UserProfileCreate,
  UserProfileRead,
  UserProfileUpdate,
} from "@/lib/types";

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

export function createShoppingRun(runId: string): Promise<RunRead> {
  return request<RunRead>(`/v1/runs/${runId}/shopping`, {
    method: "POST",
  });
}

export function getRunTrace(runId: string): Promise<RunTraceRead> {
  return request<RunTraceRead>(`/v1/runs/${runId}/trace`);
}

export function getRunStreamUrl(runId: string): string {
  return `${API_BASE_URL}/v1/runs/${runId}/stream`;
}
