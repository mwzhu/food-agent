"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createChatgptInstacartSmokeRun,
  createChatgptProfileSyncSession,
  createInstacartProfileSyncSession,
  createInstacartSmokeRun,
  createCheckoutRun,
  createRun,
  createShoppingRun,
  createWalmartProfileSyncSession,
  createWalmartSmokeRun,
  getRun,
  getRunTrace,
  getChatgptProfileSyncStatus,
  getInstacartProfileSyncStatus,
  getWalmartProfileSyncStatus,
  listRuns,
  resumeRun,
} from "@/lib/api";
import type {
  BrowserProfileSyncSession,
  BrowserProfileSyncStatus,
  ChatgptInstacartSmokeRunCreateRequest,
  CheckoutRunCreateRequest,
  InstacartSmokeRunCreateRequest,
  RunCreateRequest,
  RunRead,
  RunResumeRequest,
  RunTraceRead,
  WalmartSmokeRunCreateRequest,
} from "@/lib/types";

export function useRuns(userId: string | null, limit = 10) {
  return useQuery({
    queryKey: ["runs", userId, limit],
    queryFn: () => listRuns(userId as string, limit),
    enabled: Boolean(userId),
  });
}

export function useRun(runId: string, pollWhileRunning = false) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => {
      if (!pollWhileRunning) {
        return false;
      }
      return query.state.data?.status === "running" ? 2000 : false;
    },
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: RunCreateRequest) => createRun(payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useCreateShoppingRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => createShoppingRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useCreateCheckoutRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: CheckoutRunCreateRequest }) =>
      createCheckoutRun(runId, payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useWalmartProfileSyncStatus() {
  return useQuery({
    queryKey: ["checkout-profile-sync", "walmart"],
    queryFn: () => getWalmartProfileSyncStatus(),
  });
}

export function useCreateWalmartProfileSyncSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => createWalmartProfileSyncSession(),
    onSuccess: (session: BrowserProfileSyncSession) => {
      queryClient.setQueryData<BrowserProfileSyncStatus | undefined>(
        ["checkout-profile-sync", "walmart"],
        (current) =>
          current
            ? {
                ...current,
                configured: true,
                profile_id: session.profile_id,
              }
            : current,
      );
    },
  });
}

export function useCreateWalmartSmokeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WalmartSmokeRunCreateRequest) => createWalmartSmokeRun(payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useInstacartProfileSyncStatus() {
  return useQuery({
    queryKey: ["checkout-profile-sync", "instacart"],
    queryFn: () => getInstacartProfileSyncStatus(),
  });
}

export function useCreateInstacartProfileSyncSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => createInstacartProfileSyncSession(),
    onSuccess: (session: BrowserProfileSyncSession) => {
      queryClient.setQueryData<BrowserProfileSyncStatus | undefined>(
        ["checkout-profile-sync", "instacart"],
        (current) =>
          current
            ? {
                ...current,
                configured: true,
                profile_id: session.profile_id,
              }
            : current,
      );
    },
  });
}

export function useCreateInstacartSmokeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: InstacartSmokeRunCreateRequest) => createInstacartSmokeRun(payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useChatgptProfileSyncStatus() {
  return useQuery({
    queryKey: ["checkout-profile-sync", "chatgpt"],
    queryFn: () => getChatgptProfileSyncStatus(),
  });
}

export function useCreateChatgptProfileSyncSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => createChatgptProfileSyncSession(),
    onSuccess: (session: BrowserProfileSyncSession) => {
      queryClient.setQueryData<BrowserProfileSyncStatus | undefined>(
        ["checkout-profile-sync", "chatgpt"],
        (current) =>
          current
            ? {
                ...current,
                configured: true,
                profile_id: session.profile_id,
              }
            : current,
      );
    },
  });
}

export function useCreateChatgptInstacartSmokeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ChatgptInstacartSmokeRunCreateRequest) => createChatgptInstacartSmokeRun(payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useResumeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: RunResumeRequest }) => resumeRun(runId, payload),
    onSuccess: (run) => {
      queryClient.setQueryData<RunRead>(["run", run.run_id], run);
      queryClient.invalidateQueries({ queryKey: ["runs", run.user_id] });
    },
  });
}

export function useRunTrace(runId: string) {
  return useQuery({
    queryKey: ["run-trace", runId],
    queryFn: () => getRunTrace(runId),
  });
}
