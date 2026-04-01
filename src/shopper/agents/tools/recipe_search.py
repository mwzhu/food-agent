from __future__ import annotations

from typing import Any, Dict, List, Optional

from shopper.retrieval import QdrantRecipeStore, RecipeReranker


class RecipeSearchTool:
    def __init__(self, recipe_store: QdrantRecipeStore, reranker: RecipeReranker) -> None:
        self.recipe_store = recipe_store
        self.reranker = reranker

    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        candidates = self.recipe_store.search_recipes(query=query, filters=filters, top_k=max(top_k * 2, top_k))
        reranked = self.reranker.rerank(query=query, candidates=candidates, context=context)
        return [
            {
                "recipe": candidate.recipe.model_dump(mode="json"),
                "score": candidate.score,
                "dense_score": candidate.dense_score,
                "lexical_score": candidate.lexical_score,
                "rerank_score": candidate.rerank_score,
                "reasons": candidate.reasons,
            }
            for candidate in reranked[:top_k]
        ]
