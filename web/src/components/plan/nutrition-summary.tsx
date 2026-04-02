"use client";

import {
  Bar,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MealSlot, NutritionPlan } from "@/lib/types";
import { formatLabel } from "@/lib/utils";

type NutritionSummaryProps = {
  plan: NutritionPlan;
  meals: MealSlot[];
};

export function NutritionSummary({ plan, meals }: NutritionSummaryProps) {
  const dailyData = buildDailyNutritionData(meals, plan.daily_calories);
  const weeklyAverageCalories = Math.round(
    dailyData.reduce((sum, day) => sum + day.actualCalories, 0) / Math.max(dailyData.length, 1),
  );
  const weeklyAverageProtein = Math.round(
    dailyData.reduce((sum, day) => sum + day.proteinG, 0) / Math.max(dailyData.length, 1),
  );

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
                <p className="text-sm font-semibold">Daily calorie and macro load</p>
                <p className="text-sm text-muted-foreground">
                  Bars show macro calories by day, with the target calories overlaid as a guide.
                </p>
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={dailyData} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
                  <XAxis axisLine={false} dataKey="dayLabel" tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} />
                  <Tooltip />
                  <ReferenceLine stroke="rgba(35,48,34,0.2)" strokeDasharray="4 4" y={plan.daily_calories} />
                  <Bar dataKey="proteinCalories" fill="var(--chart-1)" radius={[10, 10, 0, 0]} stackId="macro" />
                  <Bar dataKey="carbCalories" fill="var(--chart-2)" stackId="macro" />
                  <Bar dataKey="fatCalories" fill="var(--chart-3)" stackId="macro" />
                  <Line
                    dataKey="targetCalories"
                    dot={false}
                    stroke="var(--primary)"
                    strokeWidth={2}
                    type="monotone"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Metric label="Weekly avg" value={`${weeklyAverageCalories} cal`} />
            <Metric label="Avg protein" value={`${weeklyAverageProtein}g`} />
          </div>

          <div className="rounded-[1.5rem] border border-border bg-background/75 p-4">
            <p className="text-sm font-semibold">Planner note</p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{plan.notes}</p>
          </div>

          <div className="rounded-[1.5rem] border border-border bg-background/75 p-4">
            <p className="text-sm font-semibold">Target drift by day</p>
            <div className="mt-3 space-y-3">
              {dailyData.map((day) => (
                <div key={day.day}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-foreground">{day.dayLabel}</span>
                    <span className="text-muted-foreground">
                      {day.actualCalories} / {day.targetCalories} cal
                    </span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full rounded-full ${
                        day.actualCalories <= day.targetCalories * 1.05 &&
                        day.actualCalories >= day.targetCalories * 0.95
                          ? "bg-success"
                          : "bg-primary"
                      }`}
                      style={{ width: `${Math.min(100, (day.actualCalories / day.targetCalories) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
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

function buildDailyNutritionData(meals: MealSlot[], targetCalories: number) {
  const grouped = new Map<string, { actualCalories: number; proteinG: number; carbsG: number; fatG: number }>();

  meals.forEach((meal) => {
    const current = grouped.get(meal.day) ?? { actualCalories: 0, proteinG: 0, carbsG: 0, fatG: 0 };
    current.actualCalories += meal.calories;
    current.proteinG += meal.protein_g;
    current.carbsG += meal.carbs_g;
    current.fatG += meal.fat_g;
    grouped.set(meal.day, current);
  });

  return Array.from(grouped.entries()).map(([day, values]) => ({
    day,
    dayLabel: formatLabel(day).slice(0, 3),
    targetCalories,
    actualCalories: values.actualCalories,
    proteinG: values.proteinG,
    proteinCalories: values.proteinG * 4,
    carbCalories: values.carbsG * 4,
    fatCalories: values.fatG * 9,
  }));
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.5rem] border border-border bg-background/75 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
      <span className="block text-sm text-muted-foreground">{label}</span>
      <strong className="mt-1 block text-2xl font-semibold">{value}</strong>
    </div>
  );
}
