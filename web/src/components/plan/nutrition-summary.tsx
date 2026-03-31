"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { NutritionPlan } from "@/lib/types";
import { formatLabel } from "@/lib/utils";

type NutritionSummaryProps = {
  plan: NutritionPlan;
};

export function NutritionSummary({ plan }: NutritionSummaryProps) {
  const macroData = [
    { name: "Protein", grams: plan.protein_g, fill: "var(--chart-1)" },
    { name: "Carbs", grams: plan.carbs_g, fill: "var(--chart-2)" },
    { name: "Fat", grams: plan.fat_g, fill: "var(--chart-3)" },
  ];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 pb-0 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Nutrition target
          </p>
          <CardTitle>{plan.daily_calories} daily calories</CardTitle>
        </div>
        <Badge>{formatLabel(plan.goal)}</Badge>
      </CardHeader>

      <CardContent className="grid gap-6 pt-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="TDEE" value={String(plan.tdee)} />
            <Metric label="Protein" value={`${plan.protein_g}g`} />
            <Metric label="Carbs" value={`${plan.carbs_g}g`} />
            <Metric label="Fat" value={`${plan.fat_g}g`} />
          </div>

          <div className="rounded-[1.5rem] border border-border bg-background/75 p-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold">Macro breakdown</p>
                <p className="text-sm text-muted-foreground">Recharts is now wired for future phase expansions.</p>
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={macroData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
                  <XAxis hide type="number" />
                  <YAxis
                    axisLine={false}
                    dataKey="name"
                    tickLine={false}
                    type="category"
                    width={70}
                  />
                  <Bar dataKey="grams" radius={[999, 999, 999, 999]}>
                    {macroData.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[1.5rem] border border-border bg-background/75 p-4">
            <p className="text-sm font-semibold">Planner note</p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{plan.notes}</p>
          </div>

          {plan.applied_restrictions.length ? (
            <div className="rounded-[1.5rem] border border-border bg-background/75 p-4">
              <p className="text-sm font-semibold">Applied restrictions</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {plan.applied_restrictions.map((restriction) => (
                  <Badge key={restriction} variant="secondary">
                    {restriction}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.5rem] border border-border bg-background/75 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
      <span className="block text-sm text-muted-foreground">{label}</span>
      <strong className="mt-1 block text-2xl font-semibold">{value}</strong>
    </div>
  );
}
