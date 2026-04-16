"use client";

import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelSupplementCheckout,
  continueSupplementCheckout,
  getSupplementCheckoutSession,
  startAgentCheckout,
  startSupplementCheckout,
  updateSupplementCartQuantities,
} from "@/lib/api";
import type {
  AgentCheckoutStartRequest,
  SupplementCartUpdateRequest,
  SupplementCheckoutCancelRequest,
  SupplementCheckoutContinueRequest,
  SupplementCheckoutSessionRead,
  SupplementCheckoutStartRequest,
  SupplementRunRead,
} from "@/lib/supplement-types";

export function useSupplementCheckoutSession(runId: string, storeDomain: string, enabled = true) {
  return useQuery({
    queryKey: ["supplement-checkout-session", runId, storeDomain],
    enabled: Boolean(runId) && Boolean(storeDomain) && enabled,
    queryFn: () => getSupplementCheckoutSession(runId, storeDomain),
  });
}

export function useStartSupplementCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: SupplementCheckoutStartRequest }) =>
      startSupplementCheckout(runId, payload),
    onSuccess: (run) => {
      primeSupplementRun(queryClient, run);
    },
  });
}

export function useStartAgentCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: AgentCheckoutStartRequest }) =>
      startAgentCheckout(runId, payload),
    onSuccess: (run) => {
      primeSupplementRun(queryClient, run);
    },
  });
}

export function useUpdateSupplementCartQuantities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: SupplementCartUpdateRequest }) =>
      updateSupplementCartQuantities(runId, payload),
    onSuccess: (run) => {
      primeSupplementRun(queryClient, run);
    },
  });
}

export function useContinueSupplementCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      runId,
      storeDomain,
      payload,
    }: {
      runId: string;
      storeDomain: string;
      payload: SupplementCheckoutContinueRequest;
    }) => continueSupplementCheckout(runId, storeDomain, payload),
    onSuccess: (run) => {
      primeSupplementRun(queryClient, run);
    },
  });
}

export function useCancelSupplementCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      runId,
      storeDomain,
      payload,
    }: {
      runId: string;
      storeDomain: string;
      payload: SupplementCheckoutCancelRequest;
    }) => cancelSupplementCheckout(runId, storeDomain, payload),
    onSuccess: (run) => {
      primeSupplementRun(queryClient, run);
    },
  });
}

function primeSupplementRun(queryClient: QueryClient, run: SupplementRunRead) {
  queryClient.setQueryData<SupplementRunRead>(["supplement-run", run.run_id], run);

  run.state_snapshot.checkout_sessions.forEach((checkoutSession) => {
    queryClient.setQueryData<SupplementCheckoutSessionRead>(
      ["supplement-checkout-session", run.run_id, checkoutSession.store_domain],
      checkoutSession,
    );
  });
}
