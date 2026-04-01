from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional

from shopper.config import Settings, get_settings
from shopper.retrieval.qdrant_store import ScoredRecipe


class RecipeReranker:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._cross_encoder = None

    def rerank(
        self,
        query: str,
        candidates: Iterable[ScoredRecipe],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ScoredRecipe]:
        context = context or {}
        candidate_list = list(candidates)
        cross_scores = self._cross_encoder_scores(query=query, candidates=candidate_list)

        reranked: List[ScoredRecipe] = []
        for index, candidate in enumerate(candidate_list):
            heuristic_adjustment, reasons = self._heuristic_adjustment(
                query=query,
                candidate=candidate,
                context=context,
            )
            rerank_score = candidate.score + heuristic_adjustment
            if cross_scores is not None:
                cross_score = self._sigmoid(cross_scores[index])
                rerank_score = (candidate.score * 0.45) + (cross_score * 0.45) + heuristic_adjustment
                reasons.append("cross-encoder rerank")

            reranked.append(
                replace(
                    candidate,
                    rerank_score=round(rerank_score, 4),
                    reasons=reasons,
                )
            )

        reranked.sort(key=lambda candidate: candidate.rerank_score, reverse=True)
        return reranked

    def _heuristic_adjustment(
        self,
        query: str,
        candidate: ScoredRecipe,
        context: Dict[str, Any],
    ) -> tuple[float, List[str]]:
        preferred_cuisines = {value.lower() for value in context.get("preferred_cuisines", [])}
        avoided_ingredients = {value.lower() for value in context.get("avoided_ingredients", [])}
        max_prep_time = context.get("max_prep_time")

        adjustment = 0.0
        reasons = list(candidate.reasons)
        recipe = candidate.recipe

        if preferred_cuisines and recipe.cuisine.lower() in preferred_cuisines:
            adjustment += 0.12
            reasons.append("preferred cuisine")

        if max_prep_time and recipe.prep_time_min <= max_prep_time:
            adjustment += 0.08
            reasons.append("within prep target")

        ingredient_names = {ingredient.name.lower() for ingredient in recipe.ingredients}
        if avoided_ingredients & ingredient_names:
            adjustment -= 0.18
            reasons.append("contains avoided ingredient")

        if "high protein" in query.lower() and recipe.protein_g >= 25:
            adjustment += 0.06
            reasons.append("strong protein fit")

        return adjustment, reasons

    def _cross_encoder_scores(self, query: str, candidates: List[ScoredRecipe]) -> Optional[List[float]]:
        if not candidates:
            return []

        cross_encoder = self._get_cross_encoder()
        if cross_encoder is None:
            return None

        pairs = [[query, self._recipe_text(candidate)] for candidate in candidates]
        try:
            raw_scores = cross_encoder.predict(pairs)
        except Exception:
            return None
        return [float(score) for score in raw_scores]

    def _get_cross_encoder(self):
        if self.settings.app_env == "test" or self.settings.reranker_provider != "cross_encoder":
            return None
        if self._cross_encoder is not None:
            return self._cross_encoder

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            return None

        try:
            self._cross_encoder = CrossEncoder(self.settings.reranker_model)
        except Exception:
            return None
        return self._cross_encoder

    def _recipe_text(self, candidate: ScoredRecipe) -> str:
        recipe = candidate.recipe
        ingredients = " ".join(ingredient.name for ingredient in recipe.ingredients)
        instructions = " ".join(recipe.instructions)
        tags = " ".join(recipe.tags)
        return " ".join(
            [
                recipe.name,
                recipe.cuisine,
                ingredients,
                tags,
                instructions,
                "protein {value}".format(value=recipe.protein_g),
                "prep {value}".format(value=recipe.prep_time_min),
            ]
        )

    def _sigmoid(self, value: float) -> float:
        return 1.0 / (1.0 + math.exp(-value))
