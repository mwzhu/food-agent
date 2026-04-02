from __future__ import annotations

from shopper.retrieval.corpus_builder import infer_meal_types, normalize_recipe_nlg_row, parse_quantity_and_unit


def test_parse_quantity_and_unit_handles_fractions():
    quantity, unit, remaining = parse_quantity_and_unit("2/3 c. butter or margarine")

    assert quantity == 2 / 3
    assert unit == "cup"
    assert remaining == "butter or margarine"


def test_infer_meal_types_classifies_banana_bread_as_breakfast():
    meal_types = infer_meal_types(
        title="Grandma's Banana Bread",
        normalized_text="grandma s banana bread bananas sugar flour eggs vanilla bake",
        ingredient_names=["banana", "flour", "eggs", "sugar"],
    )

    assert meal_types[0] == "breakfast"


def test_normalize_recipe_nlg_row_filters_dessert_like_entries():
    candidate = normalize_recipe_nlg_row(
        {
            "": "123",
            "title": "Double Cherry Delight",
            "ingredients": '["1 can dark sweet pitted cherries", "1 package cherry flavor gelatin", "1 tub whipped topping"]',
            "directions": '["Drain cherries.", "Dissolve gelatin and fold in whipped topping.", "Chill until set."]',
            "link": "www.example.com/recipe",
            "source": "Gathered",
            "NER": '["cherries", "gelatin", "whipped topping"]',
        }
    )

    assert candidate is None
