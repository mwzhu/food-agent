"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createInventoryItem, deleteInventoryItem, listInventory } from "@/lib/api";
import type { FridgeItemCreate, FridgeItemRead } from "@/lib/types";

export function useInventory(userId: string) {
  return useQuery({
    queryKey: ["inventory", userId],
    queryFn: () => listInventory(userId),
  });
}

export function useAddInventoryItem(userId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: FridgeItemCreate) => createInventoryItem(userId, payload),
    onSuccess: (item) => {
      queryClient.setQueryData<FridgeItemRead[]>(["inventory", userId], (current = []) => [item, ...current]);
    },
  });
}

export function useDeleteInventoryItem(userId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (itemId: number) => {
      await deleteInventoryItem(userId, itemId);
      return itemId;
    },
    onMutate: async (itemId) => {
      await queryClient.cancelQueries({ queryKey: ["inventory", userId] });
      const previous = queryClient.getQueryData<FridgeItemRead[]>(["inventory", userId]) ?? [];
      queryClient.setQueryData<FridgeItemRead[]>(
        ["inventory", userId],
        previous.filter((item) => item.item_id !== itemId),
      );
      return { previous };
    },
    onError: (_error, _itemId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["inventory", userId], context.previous);
      }
    },
  });
}
