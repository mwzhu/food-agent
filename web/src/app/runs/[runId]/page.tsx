"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { MealCalendar } from "@/components/plan/meal-calendar";
import { NutritionSummary } from "@/components/plan/nutrition-summary";
import { PhaseStepper } from "@/components/run/phase-stepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRun, useRunTrace } from "@/hooks/use-run";
import { formatDateTime, formatLabel } from "@/lib/utils";

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = typeof params.runId === "string" ? params.runId : null;
  const runQuery = useRun(runId, true);
  const traceQuery = useRunTrace(runId);

  if (!runId || runQuery.isLoading) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading run details...</p>
      </section>
    );
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Run detail
          </p>
          <CardTitle>That run could not be loaded.</CardTitle>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/runs">Back to run history</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const run = runQuery.data;
  const nutritionPlan = run.state_snapshot.nutrition_plan;

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Run detail
          </p>
          <CardTitle className="text-4xl md:text-5xl">Planning run {run.run_id.slice(0, 8)}</CardTitle>
          <p className="max-w-3xl text-base leading-7 text-muted-foreground">
            Created {formatDateTime(run.created_at)} for {run.user_id}. The state below is the
            exact phase 1 artifact returned by the backend.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={run.status === "completed" ? "success" : "default"}>{run.status}</Badge>
            <Button asChild size="sm" variant="ghost">
              <Link href="/runs">Back to history</Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <PhaseStepper runStatus={run.status} />

      <div className="grid gap-5 xl:grid-cols-[1.4fr_0.9fr]">
        <div className="space-y-5">
          {nutritionPlan ? <NutritionSummary plan={nutritionPlan} /> : null}
          {run.state_snapshot.selected_meals.length ? (
            <MealCalendar meals={run.state_snapshot.selected_meals} />
          ) : null}
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Trace</p>
              <CardTitle>Observability snapshot</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 text-sm leading-6 text-muted-foreground">
                <li>
                  <strong className="text-foreground">Trace id:</strong>{" "}
                  {traceQuery.data?.trace_id ?? String(run.state_snapshot.trace_metadata.trace_id ?? "Unavailable")}
                </li>
                <li>
                  <strong className="text-foreground">Source:</strong>{" "}
                  {traceQuery.data?.source ?? String(run.state_snapshot.trace_metadata.source ?? "Unknown")}
                </li>
                <li>
                  <strong className="text-foreground">Kind:</strong>{" "}
                  {traceQuery.data?.kind ?? String(run.state_snapshot.trace_metadata.kind ?? "Unknown")}
                </li>
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Context assembly
              </p>
              <CardTitle>What each node saw</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 text-sm leading-6 text-muted-foreground">
                {run.state_snapshot.context_metadata.map((metadata) => (
                  <li key={metadata.node_name}>
                    <strong className="text-foreground">{formatLabel(metadata.node_name)}</strong>:{" "}
                    {metadata.tokens_used}/{metadata.token_budget} tokens, fields{" "}
                    {metadata.fields_included.join(", ") || "none"}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
