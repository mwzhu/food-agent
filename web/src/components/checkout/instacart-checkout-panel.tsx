"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  useCreateCheckoutRun,
  useCreateInstacartProfileSyncSession,
  useInstacartProfileSyncStatus,
} from "@/hooks/use-run";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DEFAULT_INSTACART_START_URL = "https://www.instacart.com/grocery-delivery";

type InstacartCheckoutPanelProps = {
  runId: string;
};

export function InstacartCheckoutPanel({ runId }: InstacartCheckoutPanelProps) {
  const router = useRouter();
  const syncStatusQuery = useInstacartProfileSyncStatus();
  const createSessionMutation = useCreateInstacartProfileSyncSession();
  const createCheckoutRunMutation = useCreateCheckoutRun();
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

  const startCheckout = async () => {
    setErrorMessage(null);

    try {
      const run = await createCheckoutRunMutation.mutateAsync({
        runId,
        payload: {
          store: "Instacart",
          start_url: syncStatus?.start_url ?? DEFAULT_INSTACART_START_URL,
          allowed_domains: [],
        },
      });
      router.push(`/runs/${run.run_id}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start Instacart checkout.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Checkout</p>
        <CardTitle>Instacart browser checkout</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">
            {syncStatusQuery.isLoading
              ? "Checking Instacart login sync..."
              : syncStatus?.ready
                ? "Instacart login cookies detected in the Browser Use cloud profile."
                : "Sync Instacart login once for the most reliable checkout runs."}
          </p>
          <p className="mt-2">
            {syncStatus?.message ??
              "Open a live Browser Use session, sign into Instacart, choose your store, and confirm a saved payment method."}
          </p>
          {syncStatus?.cookie_domains.length ? (
            <p className="mt-2 text-xs">
              Cookie domains: {syncStatus.cookie_domains.slice(0, 6).join(", ")}
              {syncStatus.cookie_domains.length > 6 ? "..." : ""}
            </p>
          ) : null}
        </div>

        {sessionLink ? (
          <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
            If the popup did not open, launch the live Instacart sync session here:{" "}
            <a className="font-medium text-foreground underline underline-offset-4" href={sessionLink} rel="noreferrer" target="_blank">
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
            disabled={createCheckoutRunMutation.isPending || !syncStatus?.ready}
            onClick={() => void startCheckout()}
            type="button"
          >
            {createCheckoutRunMutation.isPending ? "Starting checkout..." : "Start Instacart checkout"}
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
  );
}
