"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { MealSlot } from "@/lib/types";
import { cn, formatLabel, formatPercent, macroFitTone } from "@/lib/utils";

type RecipeCardProps = {
  meal: MealSlot;
};

export function RecipeCard({ meal }: RecipeCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const tone = macroFitTone(meal.macro_fit_score);
  const totalMacros = meal.protein_g + meal.carbs_g + meal.fat_g || 1;
  const recipe = meal.recipe;

  return (
    <article
      className={cn(
        "rounded-[1.35rem] border p-4 transition-colors",
        tone.surfaceClass,
      )}
    >
      <button
        className="w-full text-left"
        onClick={() => setIsExpanded((current) => !current)}
        type="button"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <p className="text-[0.68rem] uppercase tracking-[0.16em] text-muted-foreground">
              {formatLabel(meal.meal_type)}
            </p>
            <h4 className="font-display text-xl leading-tight">{meal.recipe_name}</h4>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{formatLabel(meal.cuisine)}</Badge>
              <Badge className={tone.accentClass} variant="secondary">
                {tone.badgeLabel}
              </Badge>
              {meal.serving_multiplier !== 1 ? (
                <Badge variant="outline">x{meal.serving_multiplier.toFixed(2)} serving</Badge>
              ) : null}
            </div>
          </div>

          <div className="text-right text-sm text-muted-foreground">
            <p>{meal.calories} cal</p>
            <p>{meal.prep_time_min} min</p>
            <p>{formatPercent(meal.macro_fit_score)} fit</p>
          </div>
        </div>

        <div className="mt-4 space-y-2">
          <div className="flex h-2 overflow-hidden rounded-full bg-background/80">
            <span
              className="bg-[color:var(--chart-1)]"
              style={{ width: `${(meal.protein_g / totalMacros) * 100}%` }}
            />
            <span
              className="bg-[color:var(--chart-2)]"
              style={{ width: `${(meal.carbs_g / totalMacros) * 100}%` }}
            />
            <span
              className="bg-[color:var(--chart-3)]"
              style={{ width: `${(meal.fat_g / totalMacros) * 100}%` }}
            />
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
            <span>{meal.protein_g}g protein</span>
            <span>{meal.carbs_g}g carbs</span>
            <span>{meal.fat_g}g fat</span>
          </div>
        </div>
      </button>

      {isExpanded && recipe ? (
        <div className="mt-4 space-y-4 border-t border-border/70 pt-4">
          {meal.tags.length ? (
            <div className="flex flex-wrap gap-2">
              {meal.tags.map((tag) => (
                <Badge key={tag} variant="secondary">
                  {formatLabel(tag)}
                </Badge>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
            <div>
              <p className="text-sm font-semibold">Ingredients</p>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {recipe.ingredients.map((ingredient) => (
                  <li key={`${meal.recipe_id}-${ingredient.name}`}>
                    {ingredient.quantity ? `${ingredient.quantity} ${ingredient.unit ?? ""} `.trim() : ""}
                    {ingredient.name}
                    {ingredient.note ? `, ${ingredient.note}` : ""}
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="text-sm font-semibold">Method</p>
              <ol className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
                {recipe.instructions.map((step, index) => (
                  <li key={`${meal.recipe_id}-step-${index + 1}`}>
                    {index + 1}. {step}
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {recipe.source_url ? (
            <a
              className="inline-flex text-sm font-medium text-accent-foreground"
              href={recipe.source_url}
              rel="noreferrer"
              target="_blank"
            >
              View source
            </a>
          ) : (
            <p className="text-sm text-muted-foreground">Source link not available for this local corpus entry.</p>
          )}
        </div>
      ) : null}
    </article>
  );
}
