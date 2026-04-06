from __future__ import annotations

import json
from pathlib import Path

from shopper.config import Settings
from shopper.retrieval import EmbeddingService, QdrantRecipeStore
from shopper.retrieval.seed import seed_recipe_collection


def _write_corpus(tmp_path: Path) -> Path:
    corpus = [
        {
            "recipe_id": "protein-oats",
            "name": "Greek Yogurt Protein Oats",
            "cuisine": "American",
            "meal_types": ["breakfast"],
            "ingredients": [
                {"name": "greek yogurt", "quantity": 1.0, "unit": "cup", "note": ""},
                {"name": "rolled oats", "quantity": 0.5, "unit": "cup", "note": ""},
                {"name": "banana", "quantity": 1.0, "unit": None, "note": ""},
            ],
            "prep_time_min": 10,
            "calories": 420,
            "protein_g": 30,
            "carbs_g": 45,
            "fat_g": 9,
            "tags": ["vegetarian", "high-protein", "quick"],
            "instructions": ["Mix the ingredients and chill overnight."],
            "source_url": None,
        },
        {
            "recipe_id": "tofu-scramble",
            "name": "Tofu Veggie Scramble",
            "cuisine": "American",
            "meal_types": ["breakfast"],
            "ingredients": [
                {"name": "tofu", "quantity": 12.0, "unit": "oz", "note": ""},
                {"name": "spinach", "quantity": 2.0, "unit": "cup", "note": ""},
                {"name": "bell pepper", "quantity": 1.0, "unit": None, "note": ""},
            ],
            "prep_time_min": 15,
            "calories": 390,
            "protein_g": 24,
            "carbs_g": 18,
            "fat_g": 20,
            "tags": ["vegan", "gluten-free", "quick", "high-protein"],
            "instructions": ["Saute the vegetables and crumble in the tofu."],
            "source_url": None,
        },
        {
            "recipe_id": "chicken-rice-bowl",
            "name": "Chicken Rice Bowl",
            "cuisine": "Asian",
            "meal_types": ["lunch"],
            "ingredients": [
                {"name": "chicken breast", "quantity": 8.0, "unit": "oz", "note": ""},
                {"name": "rice", "quantity": 1.0, "unit": "cup", "note": ""},
                {"name": "broccoli", "quantity": 2.0, "unit": "cup", "note": ""},
            ],
            "prep_time_min": 25,
            "calories": 560,
            "protein_g": 38,
            "carbs_g": 48,
            "fat_g": 14,
            "tags": ["high-protein"],
            "instructions": ["Cook the chicken, steam the broccoli, and serve over rice."],
            "source_url": None,
        },
    ]
    corpus_path = tmp_path / "recipes.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    return corpus_path


def test_recipe_search_falls_back_to_in_memory_when_qdrant_is_unset(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_EMBEDDING_PROVIDER="local",
        SHOPPER_QDRANT_URL="",
        LANGSMITH_TRACING=False,
    )
    store = QdrantRecipeStore(
        corpus_path,
        embedding_service=EmbeddingService(settings=settings),
        settings=settings,
    )

    results = store.search_recipes(
        query="high protein breakfast under 20 minutes",
        filters={"meal_type": "breakfast", "max_prep_time": 20},
        top_k=3,
    )

    assert store.uses_qdrant is False
    assert results
    assert results[0].recipe.recipe_id == "protein-oats"
    assert results[0].recipe.prep_time_min <= 20
    assert results[0].recipe.protein_g >= 20


def test_recipe_search_uses_qdrant_filters_after_seeding(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    qdrant_path = tmp_path / "qdrant"
    settings = Settings(
        SHOPPER_APP_ENV="test",
        SHOPPER_EMBEDDING_PROVIDER="local",
        SHOPPER_QDRANT_URL=str(qdrant_path),
        SHOPPER_QDRANT_COLLECTION="recipes-test",
        LANGSMITH_TRACING=False,
    )

    seed_result = seed_recipe_collection(corpus_path, settings=settings)
    store = QdrantRecipeStore(
        corpus_path,
        embedding_service=EmbeddingService(settings=settings),
        settings=settings,
    )

    results = store.search_recipes(
        query="high protein breakfast under 20 minutes",
        filters={
            "meal_type": "breakfast",
            "max_prep_time": 20,
            "dietary_tags": ["vegan"],
            "excluded_ingredients": ["greek yogurt"],
        },
        top_k=3,
    )

    assert seed_result.recipe_count == 3
    assert seed_result.collection_name == "recipes-test"
    assert store.uses_qdrant is True
    assert [result.recipe.recipe_id for result in results] == ["tofu-scramble"]
