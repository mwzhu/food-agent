"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { ProfileHandleForm } from "@/components/profile/profile-handle-form";
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

  const handleSupplementQuickStart = async (nextUserId: string) => {
    setUserId(nextUserId);
    router.replace("/supplements");
  };

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Onboarding
          </p>
          <CardTitle className="text-4xl md:text-5xl">
            Choose the onboarding path that matches what you want to test.
          </CardTitle>
          <CardDescription className="max-w-3xl text-base">
            Supplements only need a local profile handle, while the meal planner still uses the full grocery profile
            schema backed by the API.
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

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Supplements
            </p>
            <CardTitle>Quick start with the supplement demo</CardTitle>
            <CardDescription>
              Set a local profile handle and jump directly into the supplement intake form. No grocery profile is
              required for this path.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ProfileHandleForm
              initialValue={userId}
              onSubmit={handleSupplementQuickStart}
              submitLabel="Continue to supplements"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Meal planner
            </p>
            <CardTitle>Create the full grocery planning profile</CardTitle>
            <CardDescription>
              This is the original onboarding flow for meal planning, grocery generation, inventory, and checkout lab
              testing.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>

      {errorMessage ? (
        <div className="rounded-[1.5rem] border border-accent bg-accent/70 px-4 py-3 text-sm font-medium text-accent-foreground">
          {errorMessage}
        </div>
      ) : null}

      <ProfileForm mode="create" onSubmit={handleSubmit} submitLabel="Create planner profile" />
    </section>
  );
}
