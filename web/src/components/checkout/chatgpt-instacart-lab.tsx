"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useChatgptProfileSyncStatus, useCreateChatgptInstacartSmokeRun, useCreateChatgptProfileSyncSession } from "@/hooks/use-run";
import { useUser } from "@/hooks/use-user";

const TEST_ITEMS = [
  { name: "bananas", quantityLabel: "6 count" },
  { name: "protein bar", quantityLabel: "1 count" },
];

export function ChatgptInstacartLab() {
  const router = useRouter();
  const { userId, isHydrated } = useCurrentUser();
  const userQuery = useUser(userId);
  const syncStatusQuery = useChatgptProfileSyncStatus();
  const createSessionMutation = useCreateChatgptProfileSyncSession();
  const createSmokeRunMutation = useCreateChatgptInstacartSmokeRun();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sessionLink, setSessionLink] = useState<string | null>(null);

  const syncStatus = syncStatusQuery.data;
  const automationPreview = useMemo(
    () =>
      [
        "Automated flow preview:",
        "1. Open ChatGPT in a background browser session.",
        "2. Use the Instacart app inside ChatGPT to build the two-item test cart.",
        "3. Return the cart summary back into Shopper for approval.",
        "4. After approval, reopen the same ChatGPT conversation and complete checkout there.",
      ].join("\n"),
    [],
  );

  const openSyncSession = async () => {
    setErrorMessage(null);

    try {
      const session = await createSessionMutation.mutateAsync();
      setSessionLink(session.live_url);
      if (session.provider === "browser_use_cloud") {
        window.open(session.live_url, "_blank", "noopener,noreferrer");
      }
      void syncStatusQuery.refetch();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not open a ChatGPT login sync session.");
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
      setErrorMessage(error instanceof Error ? error.message : "Could not start the automated ChatGPT Instacart test.");
    }
  };

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading automated ChatGPT checkout workspace...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <section className="space-y-6">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Automated ChatGPT test</p>
            <CardTitle>Create a profile before running the ChatGPT Instacart smoke test.</CardTitle>
            <CardDescription>
              The automated run uses your saved user profile and routes into the same approval screen as the browser
              checkout path.
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
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Automated ChatGPT test</p>
          <CardTitle className="text-3xl md:text-4xl">Instacart via ChatGPT wrapper</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            This route automates ChatGPT itself as the execution rail. Shopper launches the run, the backend drives a
            ChatGPT session to use the Instacart app, and your app still owns the approval decision before payment.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Test cart</p>
            <CardTitle>What the automated run will request</CardTitle>
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
                  <Badge variant="secondary">ChatGPT Instacart</Badge>
                </div>
              ))}
            </div>

            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
              This still uses browser automation under the hood, but only against ChatGPT. It avoids merchant checkout
              pages and keeps the same approval gate before payment.
            </div>

            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4">
              <p className="text-sm font-medium text-foreground">Operator setup</p>
              <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
                <li>Sign into ChatGPT once in the synced browser profile.</li>
                <li>Confirm the Instacart app is connected inside ChatGPT.</li>
                <li>Make sure payment is already configured in the ChatGPT Instacart flow.</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">ChatGPT session</p>
            <CardTitle>Sync login and launch</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">
                {syncStatusQuery.isLoading
                  ? "Checking ChatGPT login sync..."
                  : syncStatus?.ready
                    ? "ChatGPT cookies detected in the Browser Use cloud profile."
                    : "Sync ChatGPT login once for the automated wrapper flow."}
              </p>
              <p className="mt-2">
                {syncStatus?.message ??
                  "Open the local ChatGPT sync browser, sign in, and verify the Instacart app is connected before starting a run."}
              </p>
            </div>

            {sessionLink && syncStatus?.provider === "browser_use_cloud" ? (
              <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
                If the popup did not open, launch the live ChatGPT sync session here:{" "}
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

            {syncStatus?.provider === "local_browser" ? (
              <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
                ChatGPT sync now uses a local Chromium profile on this machine so the automated run can reuse the same
                local cookies without depending on Browser Use Cloud networking.
              </div>
            ) : null}

            <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-6">{automationPreview}</pre>
            </div>

            {errorMessage ? <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}

            <div className="flex flex-wrap gap-3">
              <Button
                disabled={createSessionMutation.isPending || syncStatusQuery.isLoading}
                onClick={() => void openSyncSession()}
                type="button"
                variant="outline"
              >
                {createSessionMutation.isPending ? "Opening live session..." : "Sync ChatGPT login"}
              </Button>
              <Button
                disabled={createSmokeRunMutation.isPending || !userQuery.data || !syncStatus?.ready}
                onClick={() => void startSmokeRun()}
                type="button"
              >
                {createSmokeRunMutation.isPending ? "Starting test..." : "Start automated test"}
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
