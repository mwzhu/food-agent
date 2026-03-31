from __future__ import annotations

from typing import Any, Dict

import httpx
from langchain_core.tools import tool

from shopper.config import get_settings


@tool("nutrition_lookup")
async def nutrition_lookup(food_query: str) -> Dict[str, Any]:
    """Look up micronutrient data from USDA FoodData Central."""

    settings = get_settings()
    if not settings.usda_api_key:
        return {
            "status": "unconfigured",
            "message": "USDA_API_KEY is not configured for nutrition lookups.",
            "query": food_query,
        }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"query": food_query, "pageSize": 1, "api_key": settings.usda_api_key},
        )
        response.raise_for_status()
        payload = response.json()
        foods = payload.get("foods", [])
        if not foods:
            return {"status": "not_found", "query": food_query}
        top_hit = foods[0]
        return {
            "status": "ok",
            "query": food_query,
            "description": top_hit.get("description"),
            "food_nutrients": top_hit.get("foodNutrients", []),
        }
