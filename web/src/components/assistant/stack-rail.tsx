"use client";

import { AlertTriangle, ShieldCheck, Wallet } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { SupplementStateSnapshot } from "@/lib/supplement-types";
import { cn, formatLabel, formatMoney } from "@/lib/utils";

type StackRailProps = {
  snapshot: SupplementStateSnapshot | null;
};

export function StackRail({ snapshot }: StackRailProps) {
  const stack = snapshot?.recommended_stack ?? null;
  const verdict = snapshot?.critic_verdict ?? null;
  const budget = snapshot?.health_profile.monthly_budget ?? null;
  const totalCost = stack ? resolveTotalCost(stack) : null;
  const isWithinBudget =
    stack?.within_budget ??
    (budget !== null && totalCost !== null ? totalCost <= budget : null);
  const budgetProgress =
    budget && totalCost !== null && budget > 0 ? Math.min((totalCost / budget) * 100, 100) : 0;

  return (
    <aside className="hidden h-full w-[320px] shrink-0 border-l border-border/70 bg-background/35 md:block">
      <div className="h-full overflow-y-auto px-4 py-5">
        <div className="space-y-4">
          <section className="rounded-[1.8rem] border border-border bg-card/85 p-5 shadow-soft">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                  Your stack
                </p>
                <h2 className="mt-2 font-display text-3xl leading-none">Current truth</h2>
              </div>
              {stack?.items.length ? <Badge variant="secondary">{stack.items.length} items</Badge> : null}
            </div>

            {stack?.items.length ? (
              <div className="mt-5 space-y-3">
                {stack.items.map((item) => (
                  <article
                    key={`${item.category}-${item.product.store_domain}-${item.product.product_id}`}
                    className="rounded-[1.25rem] border border-border/80 bg-background/70 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{item.product.title}</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant="outline">{formatLabel(item.category)}</Badge>
                          <Badge variant="secondary">{item.product.store_domain}</Badge>
                        </div>
                      </div>
                      {item.monthly_cost !== null ? (
                        <strong className="text-sm text-foreground">
                          {formatMoney(item.monthly_cost, item.product.price_range.currency || stack.currency || "USD")}
                        </strong>
                      ) : (
                        <span className="text-sm text-muted-foreground">Pending</span>
                      )}
                    </div>
                  </article>
                ))}

                <div className="rounded-[1.25rem] border border-border/80 bg-background/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-muted-foreground">Total monthly cost</span>
                    <strong className="text-lg text-foreground">
                      {totalCost !== null ? formatMoney(totalCost, stack.currency || "USD") : "Pending"}
                    </strong>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between gap-2 text-xs uppercase tracking-[0.14em] text-muted-foreground">
                      <span>Budget usage</span>
                      <span>{budget !== null ? formatMoney(budget) : "No budget"}</span>
                    </div>
                    <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-secondary/60">
                      <div
                        className={cn(
                          "h-full rounded-full bg-success transition-all",
                          isWithinBudget === false && "bg-primary",
                        )}
                        style={{ width: `${budgetProgress}%` }}
                      />
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {isWithinBudget === null
                        ? "Budget posture will appear once the stack is costed."
                        : isWithinBudget
                          ? "Within budget"
                          : "Over budget"}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-5 rounded-[1.4rem] border border-dashed border-border bg-background/55 p-5 text-sm leading-6 text-muted-foreground">
                Start a conversation to build your stack.
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              {verdict ? (
                <Badge variant={decisionVariant(verdict.decision)}>
                  <ShieldCheck className="mr-1 size-3.5" />
                  {formatLabel(verdict.decision)}
                </Badge>
              ) : null}
              {verdict ? <Badge variant="outline">{verdict.issues.length} issues</Badge> : null}
              {verdict ? <Badge variant="outline">{verdict.warnings.length} warnings</Badge> : null}
              {isWithinBudget !== null ? (
                <Badge variant={isWithinBudget ? "success" : "outline"}>
                  <Wallet className="mr-1 size-3.5" />
                  {isWithinBudget ? "Within budget" : "Over budget"}
                </Badge>
              ) : null}
            </div>
          </section>

          <details className="rounded-[1.6rem] border border-border bg-card/80 p-4 shadow-soft" open>
            <summary className="cursor-pointer list-none text-sm font-semibold text-foreground">
              Profile
            </summary>
            {snapshot ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  <MetricChip label="Age" value={String(snapshot.health_profile.age)} />
                  <MetricChip label="Sex" value={formatLabel(snapshot.health_profile.sex)} />
                  <MetricChip label="Weight" value={`${snapshot.health_profile.weight_lbs} lb`} />
                  <MetricChip label="Budget" value={formatMoney(snapshot.health_profile.monthly_budget)} />
                </div>
                <TagList label="Goals" values={snapshot.health_profile.health_goals} />
                <TagList label="Allergies" values={snapshot.health_profile.allergies} />
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">Your confirmed profile will show up here.</p>
            )}
          </details>

          <details className="rounded-[1.6rem] border border-border bg-card/80 p-4 shadow-soft">
            <summary className="cursor-pointer list-none text-sm font-semibold text-foreground">
              Refill forecast
            </summary>
            {stack?.items.length ? (
              <div className="mt-4 space-y-3">
                {stack.items.map((item) => (
                  <div
                    key={`refill-${item.category}-${item.product.product_id}`}
                    className="flex items-center justify-between gap-3 rounded-[1.1rem] border border-border/70 bg-background/65 px-3 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-foreground">{item.product.title}</p>
                      <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                        {formatLabel(item.category)}
                      </p>
                    </div>
                    <Badge variant="outline">~30 days</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">
                Refill timing appears once there's a stack to manage.
              </p>
            )}
          </details>

          {snapshot?.latest_error ? (
            <div className="rounded-[1.45rem] border border-border bg-card/80 p-4 shadow-soft">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <AlertTriangle className="size-4 text-primary" />
                Latest issue
              </div>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{snapshot.latest_error}</p>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-border/70 bg-background/65 px-3 py-3">
      <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function TagList({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      {values.length ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <Badge key={`${label}-${value}`} variant="secondary">
              {value}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">None reported.</p>
      )}
    </div>
  );
}

function resolveTotalCost(stack: NonNullable<SupplementStateSnapshot["recommended_stack"]>) {
  if (stack.total_monthly_cost !== null) {
    return stack.total_monthly_cost;
  }

  const itemCosts = stack.items
    .map((item) => item.monthly_cost)
    .filter((value): value is number => value !== null);

  if (itemCosts.length !== stack.items.length) {
    return null;
  }

  return itemCosts.reduce((total, value) => total + value, 0);
}

function decisionVariant(decision: NonNullable<SupplementStateSnapshot["critic_verdict"]>["decision"]) {
  if (decision === "passed") {
    return "success";
  }

  if (decision === "manual_review_needed") {
    return "secondary";
  }

  return "outline";
}
