"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCurrentUser } from "@/components/layout/providers";
import { RunCard } from "@/components/run/run-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCreateRun, useRuns } from "@/hooks/use-run";
import { useUser } from "@/hooks/use-user";
import { formatCurrency, formatLabel, toUserProfileBase } from "@/lib/utils";

export default function DashboardPage() {
  const router = useRouter();
  const { userId, isHydrated } = useCurrentUser();
  const userQuery = useUser(userId);
  const runsQuery = useRuns(userId, 5);
  const createRunMutation = useCreateRun();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const startRun = async () => {
    if (!userQuery.data) {
      return;
    }

    setErrorMessage(null);

    try {
      const run = await createRunMutation.mutateAsync({
        user_id: userQuery.data.user_id,
        profile: toUserProfileBase(userQuery.data),
      });
      router.push(`/runs/${run.run_id}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start a new run.");
    }
  };

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading your kitchen workspace...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <section className="space-y-6">
        <Card className="overflow-hidden">
          <CardContent className="grid gap-8 p-8 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Phase 2 experience
              </p>
              <h1 className="max-w-[12ch] font-display text-4xl leading-none md:text-6xl">
                Start by creating the profile your planner will cook for.
              </h1>
              <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                This frontend now lets you onboard, stream a live planning run, and inspect
                the retrieved recipes, nutrition fit, and critic verdict in each run.
              </p>
              <Button asChild size="lg">
                <Link href="/onboarding">Create a profile</Link>
              </Button>
            </div>

            <div className="grid gap-4 rounded-[1.75rem] border border-border bg-background/70 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
              <div>
                <p className="text-sm font-semibold">What you unlock</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  The stack now supports SSE progress streaming, richer meal cards, and
                  nutrition charts, so later shopping phases can build on the same system.
                </p>
              </div>
              <div className="space-y-3">
                <Badge>Profile persistence</Badge>
                <Badge variant="secondary">Run history</Badge>
                <Badge variant="outline">Nutrition charts</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
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
      <section className="space-y-6">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Profile issue
            </p>
            <CardTitle>Your saved profile could not be loaded.</CardTitle>
            <CardDescription>
              The current browser has a profile id saved locally, but the API does not have a
              matching user. Create a new profile to continue.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/onboarding">Create a new profile</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    );
  }

  const latestRun = runsQuery.data?.[0];
  const user = userQuery.data;

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Dashboard
          </p>
          <CardTitle className="text-4xl md:text-5xl">Planner cockpit for {user.user_id}</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            Phase 2 adds retrieval-backed meal selection, live run progress, and critic
            verification so you can inspect more of the planner's actual behavior.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardContent className="space-y-5 p-7">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Next action
            </p>
            <h2 className="max-w-[12ch] font-display text-4xl leading-none md:text-5xl">
              Generate a fresh seven-day meal plan.
            </h2>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              The planner will use your current profile, calorie target, dietary
              restrictions, and weekly rhythm to build the run.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button disabled={createRunMutation.isPending} onClick={startRun} type="button">
                {createRunMutation.isPending ? "Building plan..." : "Start a new run"}
              </Button>
              <Button asChild variant="outline">
                <Link href="/profile">Refine profile</Link>
              </Button>
            </div>
            {errorMessage ? <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Profile summary
              </p>
              <CardTitle>{formatLabel(user.goal)} plan mode</CardTitle>
            </div>
            <Badge variant="secondary">{formatLabel(user.cooking_skill)}</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <MetricCard label="Weekly budget" value={formatCurrency(user.budget_weekly)} />
            <MetricCard label="Activity" value={formatLabel(user.activity_level)} />
            <MetricCard label="Household" value={String(user.household_size)} />
            <MetricCard
              label="Restrictions"
              value={user.dietary_restrictions.length || user.allergies.length ? "Tracked" : "None"}
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Recent runs
              </p>
              <CardTitle>What the planner last produced</CardTitle>
            </div>
            <Button asChild size="sm" variant="ghost">
              <Link href="/runs">See all</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {runsQuery.isLoading ? <p className="text-muted-foreground">Loading recent activity...</p> : null}

            {!runsQuery.isLoading && latestRun ? <RunCard run={latestRun} /> : null}

            {!runsQuery.isLoading && !latestRun ? (
              <div className="rounded-[1.5rem] border border-dashed border-border bg-background/60 p-5">
                <h3 className="font-display text-2xl">No runs yet</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Your first run will appear here as soon as the planner completes.
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Phase 2 includes
            </p>
            <CardTitle>What you can use today</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm leading-6 text-muted-foreground">
              <li>Create and persist a user profile.</li>
              <li>Launch a streamed nutrition-planning run from saved preferences.</li>
              <li>Review calories, macros, meal selections, critic verdicts, and trace metadata.</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.5rem] border border-border bg-background/75 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
      <span className="block text-sm text-muted-foreground">{label}</span>
      <strong className="mt-1 block text-2xl font-semibold">{value}</strong>
    </div>
  );
}
