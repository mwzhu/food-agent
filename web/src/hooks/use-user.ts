"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createUser, getUser, updateUser } from "@/lib/api";
import type { UserProfileCreate, UserProfileRead, UserProfileUpdate } from "@/lib/types";

export function useUser(userId: string | null) {
  return useQuery({
    queryKey: ["user", userId],
    queryFn: () => getUser(userId as string),
    enabled: Boolean(userId),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: UserProfileCreate) => createUser(payload),
    onSuccess: (user) => {
      queryClient.setQueryData<UserProfileRead>(["user", user.user_id], user);
      queryClient.invalidateQueries({ queryKey: ["runs", user.user_id] });
    },
  });
}

export function useUpdateUser(userId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: UserProfileUpdate) => {
      if (!userId) {
        throw new Error("A current profile is required to update user settings.");
      }
      return updateUser(userId, payload);
    },
    onSuccess: (user) => {
      queryClient.setQueryData<UserProfileRead>(["user", user.user_id], user);
    },
  });
}
