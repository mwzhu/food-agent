"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { BudgetBar } from "@/components/grocery/budget-bar";
import { GroceryList } from "@/components/grocery/grocery-list";
import { PriceTable } from "@/components/grocery/price-table";
import { PurchaseOrders } from "@/components/grocery/purchase-orders";
import { MealCalendar } from "@/components/plan/meal-calendar";
import { NutritionSummary } from "@/components/plan/nutrition-summary";
import { RunProgress } from "@/components/run/run-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCreateShoppingRun, useRun, useRunTrace } from "@/hooks/use-run";
import { useRunStream } from "@/hooks/use-run-stream";
import { formatDateTime, formatLabel } from "@/lib/utils";

export default function RunDetailPage() {
  const router = useRouter();
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const runQuery = useRun(runId, true);
  const traceQuery = useRunTrace(runId);
  const stream = useRunStream(runId);
  const createShoppingRunMutation = useCreateShoppingRun();
  const [shoppingErrorMessage, setShoppingErrorMessage] = useState<string | null>(null);

  if (runQuery.isLoading && !runQuery.data) {
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
  const trace = traceQuery.data;
  const canStartShopping =
    run.status !== "running" &&
    run.state_snapshot.selected_meals.length > 0 &&
    run.state_snapshot.grocery_list.length === 0;

  const startShopping = async () => {
    setShoppingErrorMessage(null);

    try {
      const shoppingRun = await createShoppingRunMutation.mutateAsync(run.run_id);
      router.push(`/runs/${shoppingRun.run_id}`);
    } catch (error) {
      setShoppingErrorMessage(
        error instanceof Error ? error.message : "Could not start a shopping run from this meal plan.",
      );
    }
  };

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
            live Phase 4 artifact returned by the backend worker and streaming layer.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={run.status === "completed" ? "success" : run.status === "failed" ? "outline" : "default"}>
              {run.status}
            </Badge>
            <Button asChild size="sm" variant="ghost">
              <Link href="/runs">Back to history</Link>
            </Button>
            {trace?.url ? (
              <Button asChild size="sm" variant="outline">
                <a href={trace.url} rel="noreferrer" target="_blank">
                  View in LangSmith
                </a>
              </Button>
            ) : null}
          </div>
          {shoppingErrorMessage ? (
            <p className="text-sm font-medium text-accent-foreground">{shoppingErrorMessage}</p>
          ) : null}
        </CardHeader>
      </Card>

      <RunProgress
        currentPhase={run.state_snapshot.current_phase}
        events={stream.events}
        isStreaming={stream.isStreaming}
        phaseStatuses={run.state_snapshot.phase_statuses}
        runStatus={run.status}
      />

      <div className="grid gap-5 xl:grid-cols-[1.4fr_0.9fr]">
        <div className="space-y-5">
          {nutritionPlan ? <NutritionSummary meals={run.state_snapshot.selected_meals} plan={nutritionPlan} /> : null}
          {run.state_snapshot.selected_meals.length ? (
            <MealCalendar meals={run.state_snapshot.selected_meals} />
          ) : run.status === "running" ? (
            <Card>
              <CardHeader>
                <CardTitle>Waiting for meal selections</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Recipes will appear here as soon as planning finishes and the critic passes.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {run.state_snapshot.grocery_list.length ? (
            <div className="space-y-3">
              <div className="flex justify-end">
                <Button asChild size="sm" variant="ghost">
                  <Link href="/inventory">Edit fridge</Link>
                </Button>
              </div>
              <BudgetBar
                budgetSummary={run.state_snapshot.budget_summary}
                isShoppingActive={run.status === "running" && run.state_snapshot.current_phase === "shopping"}
                replanReason={run.state_snapshot.replan_reason}
              />
              <GroceryList items={run.state_snapshot.grocery_list} />
              <PriceTable
                items={run.state_snapshot.grocery_list}
                purchaseOrders={run.state_snapshot.purchase_orders}
                quotes={run.state_snapshot.store_quotes}
                summaries={run.state_snapshot.store_summaries}
              />
              <PurchaseOrders
                orders={run.state_snapshot.purchase_orders}
                rationale={run.state_snapshot.price_rationale}
                strategy={run.state_snapshot.price_strategy}
              />
            </div>
          ) : run.state_snapshot.phase_statuses.shopping === "running" || run.status === "running" ? (
            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Shopping</p>
                  <CardTitle>Waiting for the grocery build</CardTitle>
                </div>
                <Button asChild size="sm" variant="ghost">
                  <Link href="/inventory">Edit fridge</Link>
                </Button>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  The shopping phase will diff recipe ingredients against your saved fridge inventory, compare store
                  prices, and build purchase orders before it renders the result here.
                </p>
              </CardContent>
            </Card>
          ) : canStartShopping ? (
            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Shopping</p>
                  <CardTitle>Start shopping from the saved meal plan</CardTitle>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm" variant="ghost">
                    <Link href="/inventory">Edit fridge</Link>
                  </Button>
                  <Button
                    disabled={createShoppingRunMutation.isPending}
                    onClick={() => void startShopping()}
                    size="sm"
                    type="button"
                  >
                    {createShoppingRunMutation.isPending ? "Starting shopping..." : "Start shopping"}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  This run already has meals. Start a shopping-only follow-up run to build the grocery list even if the
                  planning critic blocked the automatic handoff.
                </p>
              </CardContent>
            </Card>
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
                  {trace?.trace_id ?? run.state_snapshot.trace_metadata.trace_id ?? "Unavailable"}
                </li>
                <li>
                  <strong className="text-foreground">Source:</strong>{" "}
                  {trace?.source ?? run.state_snapshot.trace_metadata.source ?? "Unknown"}
                </li>
                <li>
                  <strong className="text-foreground">Kind:</strong>{" "}
                  {trace?.kind ?? run.state_snapshot.trace_metadata.kind ?? "Unknown"}
                </li>
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Learned preferences
              </p>
              <CardTitle>Memory snapshot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm leading-6 text-muted-foreground">
              {run.state_snapshot.user_preferences_learned.preferred_cuisines.length ? (
                <div>
                  <strong className="text-foreground">Preferred cuisines:</strong>{" "}
                  {run.state_snapshot.user_preferences_learned.preferred_cuisines.map(formatLabel).join(", ")}
                </div>
              ) : (
                <p>No learned cuisine preferences yet.</p>
              )}

              {run.state_snapshot.retrieved_memories.length ? (
                <ul className="space-y-2">
                  {run.state_snapshot.retrieved_memories.map((memory) => (
                    <li key={memory.memory_id}>• {memory.content}</li>
                  ))}
                </ul>
              ) : (
                <p>No episodic memories were retrieved for this run.</p>
              )}
            </CardContent>
          </Card>

            <Card>
              <CardHeader>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Critic</p>
                <CardTitle>Verification verdict</CardTitle>
              </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
              {run.state_snapshot.critic_verdict ? (
                <>
                  <p>
                    <strong className="text-foreground">
                      {run.state_snapshot.critic_verdict.passed ? "Passed" : "Needs work"}
                    </strong>
                  </p>
                  {run.state_snapshot.critic_verdict.issues.length ? (
                    <ul className="space-y-2">
                      {run.state_snapshot.critic_verdict.issues.map((issue) => (
                        <li key={issue}>• {issue}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No blocking issues.</p>
                  )}
                  {run.state_snapshot.critic_verdict.warnings.length ? (
                    <ul className="space-y-2">
                      {run.state_snapshot.critic_verdict.warnings.map((warning) => (
                        <li key={warning}>• {warning}</li>
                      ))}
                    </ul>
                  ) : null}
                </>
              ) : (
                <p>Critic results will appear once the active phase finishes.</p>
              )}
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
                  <li key={`${metadata.node_name}-${metadata.tokens_used}`}>
                    <strong className="text-foreground">{formatLabel(metadata.node_name)}</strong>:{" "}
                    {metadata.tokens_used}/{metadata.token_budget} tokens, fields{" "}
                    {metadata.fields_included.join(", ") || "none"}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {run.state_snapshot.latest_error ? (
            <Card>
              <CardHeader>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Run error</p>
                <CardTitle>Latest failure</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-6 text-muted-foreground">{run.state_snapshot.latest_error}</p>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </section>
  );
}
