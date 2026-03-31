from shopper.schemas import PantryItem, ProfileFacts
from shopper.services.grocery import derive_grocery_demand
from shopper.services.nutrition import calculate_nutrition_targets
from shopper.services.planning import RECIPE_FIXTURES, select_weekly_meal_plan


def test_calculate_nutrition_targets_bulk_mode():
    profile = ProfileFacts(weight_kg=82, height_cm=182, age=31, sex="male", goal="bulk")
    targets = calculate_nutrition_targets(profile)
    assert targets.calories > 2000
    assert targets.protein_g >= 140
    assert "bulk" in targets.notes


def test_derive_grocery_demand_marks_owned_items():
    profile = ProfileFacts()
    meal_plan = select_weekly_meal_plan(profile, RECIPE_FIXTURES[:1], [])
    pantry = [
        PantryItem(name="rice", quantity=3, unit="cup", category="pantry"),
        PantryItem(name="cucumber", quantity=1, unit="unit", category="produce"),
    ]
    demand = derive_grocery_demand(meal_plan, pantry)
    demand_by_name = {item.name: item for item in demand}
    assert demand_by_name["rice"].already_have is True
    assert demand_by_name["cucumber"].already_have is False

