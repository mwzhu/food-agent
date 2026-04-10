"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { ProfileHandleForm } from "@/components/profile/profile-handle-form";
import { HealthForm } from "@/components/supplements/health-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCreateSupplementRun } from "@/hooks/use-supplement-run";
import { useUser } from "@/hooks/use-user";
import type { HealthProfile } from "@/lib/supplement-types";

const VERIFIED_STORE_DOMAINS = ["ritual.com", "transparentlabs.com", "livemomentous.com"];

export default function SupplementsPage() {
  const router = useRouter();
  const { userId, isHydrated, setUserId } = useCurrentUser();
  const userQuery = useUser(userId);
  const createSupplementRunMutation = useCreateSupplementRun();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const initialValues: Partial<HealthProfile> | undefined = userQuery.data
    ? {
        age: userQuery.data.age,
        weight_lbs: userQuery.data.weight_lbs,
        sex: userQuery.data.sex,
        allergies: userQuery.data.allergies,
      }
    : undefined;

  const startSupplementRun = async (healthProfile: HealthProfile) => {
    if (!userId) {
      return;
    }

    setErrorMessage(null);

    try {
      const run = await createSupplementRunMutation.mutateAsync({
        user_id: userId,
        health_profile: healthProfile,
      });
      router.push(`/supplements/${run.run_id}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start the supplement run.");
    }
  };

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading supplement workspace...</p>
      </section>
    );
  }

  if (!userId) {
    const saveLocalProfileHandle = async (nextUserId: string) => {
      setUserId(nextUserId);
    };

    return (
      <section className="space-y-6">
        <Card className="overflow-hidden">
          <CardContent className="grid gap-8 p-8 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Supplement quick start
              </p>
              <h1 className="max-w-[12ch] font-display text-4xl leading-none md:text-6xl">
                Pick a local profile handle and go straight into the supplement intake.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                Supplements do not need the old full grocery profile. You only need a local handle so runs can be
                grouped under one identity in this browser.
              </p>
              <div className="flex flex-wrap gap-2">
                {VERIFIED_STORE_DOMAINS.map((storeDomain) => (
                  <Badge key={storeDomain} variant="secondary">
                    {storeDomain}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="rounded-[1.75rem] border border-border bg-background/70 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              <p className="text-sm font-semibold">Continue with supplements</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Set a handle here, then the full health intake form will appear on this page.
              </p>
              <div className="mt-5">
                <ProfileHandleForm onSubmit={saveLocalProfileHandle} submitLabel="Use this profile handle" />
              </div>
              <div className="mt-5 border-t border-border pt-4">
                <p className="text-sm leading-6 text-muted-foreground">
                  Need the old meal-planner onboarding instead?
                </p>
                <Button asChild className="mt-3" size="sm" variant="ghost">
                  <Link href="/onboarding">Open planner onboarding</Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Card className="overflow-hidden">
        <CardContent className="grid gap-8 p-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-5">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Phase 5 supplement demo
            </p>
            <h1 className="max-w-[12ch] font-display text-4xl leading-none md:text-6xl">
              Build a real supplement stack and hand it off to live Shopify checkouts.
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              This flow takes a health intake, searches verified stores, compares ingredients and value, assembles a
              recommended stack, and prepares checkout URLs before approval.
            </p>
            <div className="flex flex-wrap gap-2">
              {VERIFIED_STORE_DOMAINS.map((storeDomain) => (
                <Badge key={storeDomain} variant="secondary">
                  {storeDomain}
                </Badge>
              ))}
            </div>
          </div>

          <div className="grid gap-4 rounded-[1.75rem] border border-border bg-background/70 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
            <div>
              <p className="text-sm font-semibold">What this run returns</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                You’ll get store-by-store product comparisons, a budget-aware stack recommendation, critic findings,
                and one checkout URL per approved Shopify store.
              </p>
            </div>
            <div className="space-y-3">
              <Badge>Real store search</Badge>
              <Badge variant="secondary">Multi-store carts</Badge>
              <Badge variant="outline">Approval before handoff</Badge>
            </div>
            {userQuery.isError ? (
              <p className="text-sm leading-6 text-muted-foreground">
                Your saved profile details could not be loaded, so the form is using default intake values instead.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {errorMessage ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p>
          </CardContent>
        </Card>
      ) : null}

      <HealthForm
        initialValues={initialValues}
        onSubmit={startSupplementRun}
        submitLabel={createSupplementRunMutation.isPending ? "Finding your stack..." : "Find My Stack"}
        userId={userId}
      />
    </section>
  );
}
