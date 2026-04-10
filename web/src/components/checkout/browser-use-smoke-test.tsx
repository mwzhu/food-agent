"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useCreateInstacartProfileSyncSession,
  useCreateInstacartSmokeRun,
  useInstacartProfileSyncStatus,
} from "@/hooks/use-run";
import { useUser } from "@/hooks/use-user";

const TEST_ITEMS = [
  { name: "bananas", quantityLabel: "6 count" },
  { name: "protein bar", quantityLabel: "1 count" },
];

export function BrowserUseSmokeTest() {
  const router = useRouter();
  const { userId, isHydrated } = useCurrentUser();
  const userQuery = useUser(userId);
  const syncStatusQuery = useInstacartProfileSyncStatus();
  const createSessionMutation = useCreateInstacartProfileSyncSession();
  const createSmokeRunMutation = useCreateInstacartSmokeRun();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionLink, setSessionLink] = useState<string | null>(null);

  const syncStatus = syncStatusQuery.data;

  const openSyncSession = async () => {
    setErrorMessage(null);

    try {
      const session = await createSessionMutation.mutateAsync();
      setSessionLink(session.live_url);
      window.open(session.live_url, "_blank", "noopener,noreferrer");
      void syncStatusQuery.refetch();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not open an Instacart login sync session.");
    }
  };

  const startSmokeRun = async () => {
    if (!userQuery.data) {
      return;
    }

    setErrorMessage(null);

    try {
      const run = await createSmokeRunMutation.mutateAsync({ user_id: userQuery.data.user_id });
      router.push(`/runs/${run.run_id}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start the Instacart smoke test.");
    }
  };

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading Browser Use checkout workspace...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <section className="space-y-6">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Browser Use test</p>
            <CardTitle>Create a profile before running the Instacart smoke test.</CardTitle>
            <CardDescription>
              The smoke test uses your saved user profile and routes into the normal checkout approval flow.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/onboarding">Create a profile</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Browser Use test</p>
          <CardTitle className="text-3xl md:text-4xl">Instacart two-item smoke test</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            This path keeps the existing live browser agent flow. It is useful for validating approval gating, cart
            verification, and the run detail experience, but it still depends on browser automation and retailer
            sessions.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Test cart</p>
            <CardTitle>What this run will request</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3">
              {TEST_ITEMS.map((item) => (
                <div
                  key={item.name}
                  className="flex items-center justify-between rounded-[1.25rem] border border-border bg-background/70 px-4 py-3"
                >
                  <div>
                    <p className="font-medium text-foreground">{item.name}</p>
                    <p className="text-sm text-muted-foreground">{item.quantityLabel}</p>
                  </div>
                  <Badge variant="secondary">Instacart</Badge>
                </div>
              ))}
            </div>

            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
              The smoke test uses the live Instacart checkout agent, human approval gate, and payment flow. It just
              keeps the requested cart intentionally tiny.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Instacart session</p>
            <CardTitle>Login sync and launch</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">
                {syncStatusQuery.isLoading
                  ? "Checking Instacart login sync..."
                  : syncStatus?.ready
                    ? "Instacart cookies detected in the Browser Use cloud profile."
                    : "Sync Instacart login once for the most reliable smoke-test runs."}
              </p>
              <p className="mt-2">
                {syncStatus?.message ??
                  "Open a live Browser Use session, sign into Instacart, pick your store, and confirm a saved payment method."}
              </p>
            </div>

            {sessionLink ? (
              <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
                If the popup did not open, launch the live Instacart sync session here:{" "}
                <a
                  className="font-medium text-foreground underline underline-offset-4"
                  href={sessionLink}
                  rel="noreferrer"
                  target="_blank"
                >
                  open Browser Use live session
                </a>
              </div>
            ) : null}

            {errorMessage ? <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}

            <div className="flex flex-wrap gap-3">
              <Button
                disabled={createSessionMutation.isPending || syncStatusQuery.isLoading}
                onClick={() => void openSyncSession()}
                type="button"
                variant="outline"
              >
                {createSessionMutation.isPending ? "Opening live session..." : "Sync Instacart login"}
              </Button>
              <Button
                disabled={createSmokeRunMutation.isPending || !userQuery.data || !syncStatus?.ready}
                onClick={() => void startSmokeRun()}
                type="button"
              >
                {createSmokeRunMutation.isPending ? "Starting test..." : "Start two-item test"}
              </Button>
              <Button
                disabled={syncStatusQuery.isFetching}
                onClick={() => void syncStatusQuery.refetch()}
                type="button"
                variant="ghost"
              >
                Refresh status
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
