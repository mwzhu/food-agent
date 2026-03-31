"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { ProfileForm } from "@/components/profile/profile-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCreateUser } from "@/hooks/use-user";
import type { UserProfileCreate, UserProfileUpdate } from "@/lib/types";

export default function OnboardingPage() {
  const router = useRouter();
  const { userId, setUserId } = useCurrentUser();
  const createUserMutation = useCreateUser();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (payload: UserProfileCreate | UserProfileUpdate) => {
    setErrorMessage(null);

    try {
      const user = await createUserMutation.mutateAsync(payload as UserProfileCreate);
      setUserId(user.user_id);
      router.replace("/");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not create the profile.");
    }
  };

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Onboarding
          </p>
          <CardTitle className="text-4xl md:text-5xl">
            Build the profile your planner will use for every run.
          </CardTitle>
          <CardDescription className="max-w-3xl text-base">
            The form mirrors the backend schema for phase 1, then stores the active profile
            id locally so you can move through the product like a real user.
          </CardDescription>
        </CardHeader>
        {userId ? (
          <CardContent className="flex flex-wrap items-center gap-3 pt-0">
            <Badge variant="secondary">Current profile: {userId}</Badge>
            <Button asChild size="sm" variant="ghost">
              <Link href="/">Back to dashboard</Link>
            </Button>
          </CardContent>
        ) : null}
      </Card>

      {errorMessage ? (
        <div className="rounded-[1.5rem] border border-accent bg-accent/70 px-4 py-3 text-sm font-medium text-accent-foreground">
          {errorMessage}
        </div>
      ) : null}

      <ProfileForm mode="create" onSubmit={handleSubmit} submitLabel="Create profile" />
    </section>
  );
}
