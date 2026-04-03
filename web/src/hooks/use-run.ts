"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createRun, getRun, getRunTrace, listRuns } from "@/lib/api";
import type { RunCreateRequest, RunRead, RunTraceRead } from "@/lib/types";

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

export function useRunTrace(runId: string) {
  return useQuery({
    queryKey: ["run-trace", runId],
    queryFn: () => getRunTrace(runId),
  });
}
