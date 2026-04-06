"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BudgetSummary } from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";

type BudgetBarProps = {
  budgetSummary: BudgetSummary | null;
  replanReason: string | null;
  isPlanningActive: boolean;
};

export function BudgetBar({ budgetSummary, replanReason, isPlanningActive }: BudgetBarProps) {
  if (!budgetSummary) {
    return null;
  }

  const ratio = budgetSummary.utilization;
  const progressWidth = `${Math.min(Math.max(ratio * 100, 0), 100)}%`;
  const toneClass =
    ratio < 0.8
      ? "bg-success"
      : ratio <= 1
        ? "bg-[color:var(--chart-2)]"
        : "bg-primary";

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Budget</p>
          <CardTitle>Weekly grocery budget tracking</CardTitle>
        </div>
        <Badge variant={budgetSummary.within_budget ? "success" : "outline"}>
          {budgetSummary.within_budget ? "Within budget" : "Over budget"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Metric label="Planned spend" value={formatCurrency(budgetSummary.total_cost, { minimumFractionDigits: 2 })} />
          <Metric label="Budget" value={formatCurrency(budgetSummary.budget)} />
          <Metric
            label={budgetSummary.within_budget ? "Remaining" : "Overage"}
            value={formatCurrency(
              budgetSummary.within_budget
                ? Math.max(0, budgetSummary.budget - budgetSummary.total_cost)
                : budgetSummary.overage,
              { minimumFractionDigits: 2 },
            )}
          />
        </div>

        <div className="space-y-2">
          <div className="h-3 overflow-hidden rounded-full bg-muted">
            <div className={cn("h-full rounded-full transition-all", toneClass)} style={{ width: progressWidth }} />
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{Math.round(budgetSummary.utilization * 100)}% of weekly budget</span>
            <span>{formatCurrency(budgetSummary.budget)}</span>
          </div>
        </div>

        {replanReason ? (
          <div className="rounded-[1.1rem] border border-border bg-background/70 p-4 text-sm leading-6 text-muted-foreground">
            <strong className="text-foreground">
              {isPlanningActive && !budgetSummary.within_budget ? "Replanning..." : "Budget note"}
            </strong>{" "}
            {replanReason}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-border bg-background/75 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <strong className="mt-1 block text-xl text-foreground">{value}</strong>
    </div>
  );
}
