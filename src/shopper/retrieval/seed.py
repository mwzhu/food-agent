from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from shopper.config import Settings, get_settings
from shopper.retrieval.embeddings import EmbeddingService
from shopper.retrieval.qdrant_store import (
    SparseTextVectorizer,
    build_qdrant_client,
    ensure_qdrant_collection,
    load_recipe_corpus,
    recipe_payload,
    recipe_point_id,
    recipe_searchable_text,
)
from shopper.schemas import RecipeRecord


@dataclass
class SeedResult:
    recipe_count: int
    batch_count: int
    vector_size: int
    collection_name: str
    sparse_enabled: bool


def seed_recipe_corpus(corpus_path: Union[str, Path]) -> List[RecipeRecord]:
    return load_recipe_corpus(Path(corpus_path))


def seed_recipe_collection(
    corpus_path: Union[str, Path],
    settings: Optional[Settings] = None,
    embedding_service: Optional[EmbeddingService] = None,
) -> SeedResult:
    settings = settings or get_settings()
    if not settings.qdrant_url:
        raise RuntimeError("SHOPPER_QDRANT_URL must be set to seed Qdrant.")

    corpus_path = Path(corpus_path)
    recipes = load_recipe_corpus(corpus_path)
    if not recipes:
        raise RuntimeError("Recipe corpus is empty; nothing to seed.")

    embedding_service = embedding_service or EmbeddingService(settings=settings)
    client = build_qdrant_client(settings)
    sparse_vectorizer = SparseTextVectorizer()
    batch_size = max(settings.qdrant_batch_size, 1)

    first_embedding = embedding_service.embed_text(recipe_searchable_text(recipes[0]))
    vector_size = len(first_embedding)
    if vector_size == 0:
        raise RuntimeError("Embedding service returned an empty vector for recipe seeding.")
    ensure_qdrant_collection(client, settings, vector_size)

    from qdrant_client import models

    dense_vector_name = settings.qdrant_dense_vector_name
    sparse_vector_name = settings.qdrant_sparse_vector_name
    batch_count = 0

    for start in range(0, len(recipes), batch_size):
        batch = recipes[start:start + batch_size]
        searchable_texts = [recipe_searchable_text(recipe) for recipe in batch]
        dense_vectors = embedding_service.embed_texts(searchable_texts)
        points = []

        for recipe, searchable_text, dense_vector in zip(batch, searchable_texts, dense_vectors):
            payload = recipe_payload(recipe)
            vectors = {dense_vector_name: dense_vector}
            if settings.qdrant_enable_sparse:
                indices, values = sparse_vectorizer.vectorize(searchable_text)
                vectors[sparse_vector_name] = models.SparseVector(indices=indices, values=values)
            points.append(
                models.PointStruct(
                    id=recipe_point_id(recipe.recipe_id),
                    vector=vectors,
                    payload=payload,
                )
            )

        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
            wait=True,
        )
        batch_count += 1

    return SeedResult(
        recipe_count=len(recipes),
        batch_count=batch_count,
        vector_size=vector_size,
        collection_name=settings.qdrant_collection,
        sparse_enabled=settings.qdrant_enable_sparse,
    )
