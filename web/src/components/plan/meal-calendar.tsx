"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RecipeCard } from "@/components/plan/recipe-card";
import type { MealSlot } from "@/lib/types";
import { formatLabel, groupMealsByDay } from "@/lib/utils";

type MealCalendarProps = {
  meals: MealSlot[];
};

export function MealCalendar({ meals }: MealCalendarProps) {
  const groups = groupMealsByDay(meals);
  const [selectedDay, setSelectedDay] = useState(groups.find((group) => group.meals.length)?.day ?? groups[0]?.day);
  const activeGroup = groups.find((group) => group.day === selectedDay) ?? groups[0];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 pb-0 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Meal plan</p>
          <CardTitle>Seven-day meal calendar</CardTitle>
        </div>
        <Badge>{meals.length} meals</Badge>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        <div className="flex gap-2 overflow-x-auto pb-1 md:hidden">
          {groups.map((group) => (
            <button
              key={group.day}
              className={`rounded-full border px-3 py-2 text-sm ${
                selectedDay === group.day
                  ? "border-primary bg-accent text-accent-foreground"
                  : "border-border bg-background/80 text-muted-foreground"
              }`}
              onClick={() => setSelectedDay(group.day)}
              type="button"
            >
              {formatLabel(group.day).slice(0, 3)}
            </button>
          ))}
        </div>

        {activeGroup ? (
          <div className="space-y-4 md:hidden">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-2xl">{formatLabel(activeGroup.day)}</h3>
              <span className="text-sm text-muted-foreground">
                {activeGroup.meals.reduce((sum, meal) => sum + meal.calories, 0)} cal
              </span>
            </div>
            {activeGroup.meals.map((meal) => (
              <RecipeCard key={`${activeGroup.day}-${meal.meal_type}-${meal.recipe_id}`} meal={meal} />
            ))}
          </div>
        ) : null}

        <div className="hidden gap-4 xl:grid xl:grid-cols-7">
          {groups.map((group) => (
            <article
              key={group.day}
              className="rounded-[1.5rem] border border-border bg-background/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
            >
              <div className="flex items-center justify-between border-b border-border/80 pb-4">
                <h3 className="font-display text-xl">{formatLabel(group.day)}</h3>
                <span className="text-xs text-muted-foreground">
                  {group.meals.reduce((sum, meal) => sum + meal.calories, 0)} cal
                </span>
              </div>

              <div className="mt-4 space-y-4">
                {group.meals.map((meal) => (
                  <RecipeCard key={`${group.day}-${meal.meal_type}-${meal.recipe_id}`} meal={meal} />
                ))}
              </div>
            </article>
          ))}
        </div>

        <div className="hidden gap-4 md:grid xl:hidden md:grid-cols-2">
          {groups.map((group) => (
            <article
              key={group.day}
              className="rounded-[1.5rem] border border-border bg-background/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
            >
              <div className="flex items-center justify-between border-b border-border/80 pb-4">
                <h3 className="font-display text-xl">{formatLabel(group.day)}</h3>
                <span className="text-xs text-muted-foreground">
                  {group.meals.reduce((sum, meal) => sum + meal.calories, 0)} cal
                </span>
              </div>

              <div className="mt-4 space-y-4">
                {group.meals.map((meal) => (
                  <RecipeCard key={`${group.day}-${meal.meal_type}-${meal.recipe_id}`} meal={meal} />
                ))}
              </div>
            </article>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
