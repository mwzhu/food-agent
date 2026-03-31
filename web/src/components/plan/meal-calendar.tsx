import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MealSlot } from "@/lib/types";
import { formatLabel, groupMealsByDay } from "@/lib/utils";

type MealCalendarProps = {
  meals: MealSlot[];
};

export function MealCalendar({ meals }: MealCalendarProps) {
  const groups = groupMealsByDay(meals);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 pb-0 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Meal plan</p>
          <CardTitle>Seven-day starter lineup</CardTitle>
        </div>
        <Badge>{meals.length} meals</Badge>
      </CardHeader>

      <CardContent className="grid gap-4 pt-6 md:grid-cols-2 xl:grid-cols-3">
        {groups.map((group) => (
          <article
            key={group.day}
            className="rounded-[1.5rem] border border-border bg-background/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
          >
            <div className="flex flex-col gap-2 border-b border-border/80 pb-4 md:flex-row md:items-start md:justify-between">
              <h3 className="font-display text-xl">{formatLabel(group.day)}</h3>
              <span className="text-sm text-muted-foreground">
                {group.meals.reduce((sum, meal) => sum + meal.calories, 0)} cal
              </span>
            </div>

            <div className="mt-4 space-y-4">
              {group.meals.map((meal) => (
                <div
                  key={meal.recipe_id}
                  className="flex flex-col gap-3 border-t border-border/70 pt-4 first:border-t-0 first:pt-0 md:flex-row md:items-start md:justify-between"
                >
                  <div>
                    <p className="mb-1 text-[0.7rem] uppercase tracking-[0.16em] text-muted-foreground">
                      {formatLabel(meal.meal_type)}
                    </p>
                    <strong>{meal.recipe_name}</strong>
                  </div>
                  <div className="text-sm text-muted-foreground md:text-right">
                    <span>{meal.calories} cal</span>
                    <span className="block">{meal.prep_time_min} min</span>
                  </div>
                </div>
              ))}
            </div>
          </article>
        ))}
      </CardContent>
    </Card>
  );
}
