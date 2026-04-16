"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, getSupplementBuyerProfile, upsertSupplementBuyerProfile } from "@/lib/api";
import type { SupplementBuyerProfileRead, SupplementBuyerProfileUpsertRequest } from "@/lib/supplement-types";

export function useSupplementBuyerProfile(runId: string, enabled = true) {
  return useQuery({
    queryKey: ["supplement-buyer-profile", runId],
    enabled: Boolean(runId) && enabled,
    queryFn: async () => {
      try {
        return await getSupplementBuyerProfile(runId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
  });
}

export function useUpsertSupplementBuyerProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: SupplementBuyerProfileUpsertRequest }) =>
      upsertSupplementBuyerProfile(runId, payload),
    onSuccess: (buyerProfile, variables) => {
      queryClient.setQueryData<SupplementBuyerProfileRead | null>(
        ["supplement-buyer-profile", variables.runId],
        buyerProfile,
      );
      void queryClient.invalidateQueries({ queryKey: ["supplement-run", variables.runId] });
    },
  });
}
