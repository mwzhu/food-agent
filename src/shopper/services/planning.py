from __future__ import annotations

from dataclasses import dataclass

from shopper.schemas import MealPlan, ProfileFacts, RecipeCandidate


RECIPE_FIXTURES = [
    RecipeCandidate(
        recipe_id="r1",
        name="Greek Chicken Bowls",
        tags=["high-protein", "weekday", "mediterranean"],
        prep_time_minutes=25,
        calories=620,
        protein_g=48,
        carbs_g=45,
        fat_g=24,
        ingredients=[
            {"name": "chicken breast", "quantity": 1.5, "unit": "lb", "category": "protein"},
            {"name": "rice", "quantity": 2, "unit": "cup", "category": "pantry"},
            {"name": "cucumber", "quantity": 2, "unit": "unit", "category": "produce"},
        ],
    ),
    RecipeCandidate(
        recipe_id="r2",
        name="Tofu Stir Fry",
        tags=["vegetarian", "weekday", "high-protein"],
        prep_time_minutes=20,
        calories=540,
        protein_g=32,
        carbs_g=50,
        fat_g=20,
        ingredients=[
            {"name": "tofu", "quantity": 2, "unit": "block", "category": "protein"},
            {"name": "broccoli", "quantity": 2, "unit": "head", "category": "produce"},
            {"name": "soy sauce", "quantity": 0.5, "unit": "cup", "category": "pantry"},
        ],
    ),
    RecipeCandidate(
        recipe_id="r3",
        name="Salmon Sweet Potato Plates",
        tags=["high-protein", "omega-3", "weekday"],
        prep_time_minutes=30,
        calories=680,
        protein_g=42,
        carbs_g=48,
        fat_g=28,
        ingredients=[
            {"name": "salmon fillet", "quantity": 1.5, "unit": "lb", "category": "protein"},
            {"name": "sweet potato", "quantity": 4, "unit": "unit", "category": "produce"},
            {"name": "spinach", "quantity": 1, "unit": "bag", "category": "produce"},
        ],
    ),
]


@dataclass
class RecipeRetriever:
    recipes: list[RecipeCandidate]

    def search(self, profile: ProfileFacts, limit: int = 3) -> list[RecipeCandidate]:
        disallowed = {item.lower() for item in profile.dislikes + profile.allergies}
        matches: list[RecipeCandidate] = []
        for recipe in self.recipes:
            recipe_blob = f"{recipe.name} {' '.join(recipe.tags)} {' '.join(i.name for i in recipe.ingredients)}".lower()
            if any(token in recipe_blob for token in disallowed):
                continue
            if "vegetarian" in profile.dietary_restrictions and "vegetarian" not in recipe.tags:
                continue
            if recipe.prep_time_minutes > profile.weekday_time_limit_minutes + 10:
                continue
            matches.append(recipe)
        return matches[:limit] or self.recipes[:limit]


def select_weekly_meal_plan(
    profile: ProfileFacts,
    candidate_recipes: list[RecipeCandidate],
    relevant_memories: list[str],
) -> MealPlan:
    if not candidate_recipes:
        candidate_recipes = RECIPE_FIXTURES[:2]
    rationale = "Selected fast, high-satiety meals aligned to weekly constraints."
    if relevant_memories:
        rationale += f" Memory signals considered: {' | '.join(relevant_memories[:2])}."
    selected = candidate_recipes[: min(3, len(candidate_recipes))]
    return MealPlan(
        recipe_ids=[recipe.recipe_id for recipe in selected],
        recipes=selected,
        rationale=rationale,
    )

