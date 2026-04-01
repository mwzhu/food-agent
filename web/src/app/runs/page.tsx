"use client";

import Link from "next/link";

import { useCurrentUser } from "@/components/layout/providers";
import { RunCard } from "@/components/run/run-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useRuns } from "@/hooks/use-run";

export default function RunsPage() {
  const { userId, isHydrated } = useCurrentUser();
  const runsQuery = useRuns(userId, 20);

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading run history...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Run history
          </p>
          <CardTitle>Create a profile before reviewing planner runs.</CardTitle>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/onboarding">Create a profile</Link>
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
            Run history
          </p>
          <CardTitle className="text-4xl md:text-5xl">All recorded planning runs for {userId}</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            Each run preserves the streamed Phase 2 state snapshot so you can review what the
            planner searched, selected, and verified before later shopping phases arrive.
          </CardDescription>
        </CardHeader>
      </Card>

      {runsQuery.isError ? (
        <Card>
          <CardHeader>
            <CardTitle>Could not load run history</CardTitle>
            <CardDescription>
              Check that the FastAPI backend is running and reachable from the web app.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {runsQuery.isLoading ? (
        <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
          <p className="text-muted-foreground">Loading runs...</p>
        </section>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError && runsQuery.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {runsQuery.data.map((run) => (
            <RunCard key={run.run_id} run={run} />
          ))}
        </div>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError && !runsQuery.data?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>No runs yet</CardTitle>
            <CardDescription>
              Go back to the dashboard and launch your first meal-planning run.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/">Open dashboard</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}
