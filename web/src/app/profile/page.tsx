"use client";

import Link from "next/link";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { ProfileForm } from "@/components/profile/profile-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useUpdateUser, useUser } from "@/hooks/use-user";
import type { UserProfileCreate, UserProfileUpdate } from "@/lib/types";

export default function ProfilePage() {
  const { userId, isHydrated } = useCurrentUser();
  const userQuery = useUser(userId);
  const updateUserMutation = useUpdateUser(userId);
  const [notice, setNotice] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (payload: UserProfileCreate | UserProfileUpdate) => {
    setNotice(null);
    setErrorMessage(null);

    try {
      await updateUserMutation.mutateAsync(payload as UserProfileUpdate);
      setNotice("Profile saved. New runs will use your updated settings.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not update the profile.");
    }
  };

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading profile settings...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            No active profile
          </p>
          <CardTitle>Create a profile before editing settings.</CardTitle>
          <CardDescription>
            This app stores the active user id locally in the browser for phase 1.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/onboarding">Create a profile</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (userQuery.isLoading) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading profile...</p>
      </section>
    );
  }

  if (userQuery.isError || !userQuery.data) {
    return (
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Missing profile
          </p>
          <CardTitle>That profile is not available from the API.</CardTitle>
          <CardDescription>Create a fresh one to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/onboarding">Create a new profile</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Profile
          </p>
          <CardTitle className="text-4xl md:text-5xl">
            Fine-tune {userId}&apos;s planning inputs.
          </CardTitle>
          <CardDescription className="max-w-3xl text-base">
            Editing here updates the backend user profile, and the dashboard will use the
            new values the next time you kick off a run.
          </CardDescription>
        </CardHeader>
      </Card>

      {notice ? (
        <div className="rounded-[1.5rem] border border-success bg-success-soft px-4 py-3 text-sm font-medium text-success">
          {notice}
        </div>
      ) : null}
      {errorMessage ? (
        <div className="rounded-[1.5rem] border border-accent bg-accent/70 px-4 py-3 text-sm font-medium text-accent-foreground">
          {errorMessage}
        </div>
      ) : null}

      <ProfileForm
        initialUser={userQuery.data}
        mode="edit"
        onSubmit={handleSubmit}
        submitLabel={updateUserMutation.isPending ? "Saving..." : "Save profile"}
      />
    </section>
  );
}
