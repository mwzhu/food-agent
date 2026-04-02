from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from shopper.config import Settings, get_settings
from shopper.retrieval.embeddings import EmbeddingService
from shopper.schemas import RecipeRecord


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
RESTRICTION_TAGS = {
    "vegetarian": "vegetarian",
    "vegan": "vegan",
    "gluten_free": "gluten-free",
    "gluten-free": "gluten-free",
    "dairy_free": "dairy-free",
    "dairy-free": "dairy-free",
}
RECIPE_ID_NAMESPACE = uuid.UUID("5f8685d8-17b5-4c5d-a633-7370eb8e97f5")
DEFAULT_DENSE_VECTOR_NAME = "dense"
DEFAULT_SPARSE_VECTOR_NAME = "sparse"
QDRANT_HNSW_EF = 128
QDRANT_PREFETCH_LIMIT = 32


@dataclass
class RecipeSearchFilters:
    meal_type: Optional[str] = None
    cuisine: Optional[str] = None
    max_prep_time: Optional[int] = None
    dietary_tags: List[str] = field(default_factory=list)
    calorie_range: Optional[Tuple[int, int]] = None
    excluded_ingredients: List[str] = field(default_factory=list)


@dataclass
class ScoredRecipe:
    recipe: RecipeRecord
    score: float
    dense_score: float
    lexical_score: float
    rerank_score: float
    reasons: List[str] = field(default_factory=list)


def load_recipe_corpus(corpus_path: Path) -> List[RecipeRecord]:
    payload = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    return [RecipeRecord.model_validate(item) for item in payload]


def recipe_searchable_text(recipe: RecipeRecord) -> str:
    ingredient_names = " ".join(ingredient.name for ingredient in recipe.ingredients)
    tags = " ".join(recipe.tags)
    instructions = " ".join(recipe.instructions)
    meal_types = " ".join(recipe.meal_types)
    return " ".join([recipe.name, recipe.cuisine, ingredient_names, tags, instructions, meal_types])


def recipe_point_id(recipe_id: str) -> str:
    return str(uuid.uuid5(RECIPE_ID_NAMESPACE, recipe_id))


def recipe_payload(recipe: RecipeRecord) -> Dict[str, Any]:
    ingredient_names = [
        " ".join(TOKEN_PATTERN.findall(ingredient.name.lower()))
        for ingredient in recipe.ingredients
        if ingredient.name
    ]
    ingredient_names = [name for name in ingredient_names if name]
    tags = sorted({tag.lower() for tag in recipe.tags})
    dietary_restrictions = sorted(
        {
            normalized
            for tag in tags
            if (normalized := RESTRICTION_TAGS.get(tag))
        }
    )
    return {
        "recipe_id": recipe.recipe_id,
        "cuisine": recipe.cuisine.lower(),
        "meal_types": list(recipe.meal_types),
        "prep_time_min": recipe.prep_time_min,
        "calories": recipe.calories,
        "protein_g": recipe.protein_g,
        "tags": tags,
        "dietary_restrictions": dietary_restrictions,
        "ingredient_names": ingredient_names,
        "ingredient_text": " ".join(ingredient_names),
    }


class SparseTextVectorizer:
    def vectorize(self, text: str) -> tuple[List[int], List[float]]:
        token_counts = Counter(TOKEN_PATTERN.findall(text.lower()))
        if not token_counts:
            return [], []

        sparse_values: Dict[int, float] = {}
        for token, count in token_counts.items():
            bucket = self._bucket_for_token(token)
            sparse_values[bucket] = sparse_values.get(bucket, 0.0) + (1.0 + math.log(count))

        ordered = sorted(sparse_values.items())
        return [index for index, _ in ordered], [round(value, 6) for _, value in ordered]

    def _bucket_for_token(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % 2_147_483_647


def build_qdrant_client(settings: Settings):
    from qdrant_client import QdrantClient

    if not settings.qdrant_url:
        raise RuntimeError("SHOPPER_QDRANT_URL is not configured.")
    if settings.qdrant_url == ":memory:":
        return QdrantClient(":memory:")
    if "://" not in settings.qdrant_url:
        return QdrantClient(path=settings.qdrant_url)
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout_s,
    )


def ensure_qdrant_collection(client, settings: Settings, vector_size: int) -> None:
    from qdrant_client import models

    dense_vector_name = settings.qdrant_dense_vector_name or DEFAULT_DENSE_VECTOR_NAME
    sparse_vector_name = settings.qdrant_sparse_vector_name or DEFAULT_SPARSE_VECTOR_NAME

    if not client.collection_exists(settings.qdrant_collection):
        sparse_vectors_config = None
        if settings.qdrant_enable_sparse:
            sparse_vectors_config = {
                sparse_vector_name: models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=True),
                    modifier=models.Modifier.IDF,
                )
            }
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config={
                dense_vector_name: models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                    hnsw_config=models.HnswConfigDiff(m=32, ef_construct=128),
                )
            },
            sparse_vectors_config=sparse_vectors_config,
            on_disk_payload=True,
        )
        _ensure_payload_indexes(client, settings)
        return

    collection = client.get_collection(settings.qdrant_collection)
    vectors = collection.config.params.vectors
    if not isinstance(vectors, Mapping) or dense_vector_name not in vectors:
        raise RuntimeError(
            "Qdrant collection '{name}' is missing the '{vector}' dense vector.".format(
                name=settings.qdrant_collection,
                vector=dense_vector_name,
            )
        )
    dense_config = vectors[dense_vector_name]
    if dense_config.size != vector_size:
        raise RuntimeError(
            "Qdrant collection '{name}' expects dense vectors of size {expected}, but embeddings are size {actual}.".format(
                name=settings.qdrant_collection,
                expected=dense_config.size,
                actual=vector_size,
            )
        )
    if settings.qdrant_enable_sparse:
        sparse_vectors = collection.config.params.sparse_vectors or {}
        if sparse_vector_name not in sparse_vectors:
            raise RuntimeError(
                "Qdrant collection '{name}' is missing the '{vector}' sparse vector.".format(
                    name=settings.qdrant_collection,
                    vector=sparse_vector_name,
                )
            )
    _ensure_payload_indexes(client, settings)


def _ensure_payload_indexes(client, settings: Settings) -> None:
    from qdrant_client import models

    if settings.qdrant_url == ":memory:" or (settings.qdrant_url and "://" not in settings.qdrant_url):
        return

    payload_indexes = [
        ("recipe_id", models.PayloadSchemaType.KEYWORD),
        ("cuisine", models.PayloadSchemaType.KEYWORD),
        ("meal_types", models.PayloadSchemaType.KEYWORD),
        ("prep_time_min", models.PayloadSchemaType.INTEGER),
        ("calories", models.PayloadSchemaType.INTEGER),
        ("protein_g", models.PayloadSchemaType.INTEGER),
        ("tags", models.PayloadSchemaType.KEYWORD),
        ("dietary_restrictions", models.PayloadSchemaType.KEYWORD),
        (
            "ingredient_text",
            models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
            ),
        ),
    ]
    for field_name, field_schema in payload_indexes:
        try:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=field_schema,
            )
        except Exception:
            continue


class QdrantRecipeStore:
    def __init__(
        self,
        corpus_path: Path,
        embedding_service: Optional[EmbeddingService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.corpus_path = Path(corpus_path)
        self.settings = settings or get_settings()
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)
        self._recipes = load_recipe_corpus(self.corpus_path)
        self._recipes_by_id = {recipe.recipe_id: recipe for recipe in self._recipes}
        if self.settings.qdrant_url:
            self._backend: Union[_InMemoryRecipeSearchBackend, _QdrantSearchBackend] = _QdrantSearchBackend(
                embedding_service=self.embedding_service,
                recipes_by_id=self._recipes_by_id,
                settings=self.settings,
            )
        else:
            self._backend = _InMemoryRecipeSearchBackend(
                recipes=self._recipes,
                embedding_service=self.embedding_service,
            )

    @property
    def recipes(self) -> List[RecipeRecord]:
        return list(self._recipes)

    @property
    def uses_qdrant(self) -> bool:
        return isinstance(self._backend, _QdrantSearchBackend)

    def get_recipe(self, recipe_id: str) -> Optional[RecipeRecord]:
        return self._recipes_by_id.get(recipe_id)

    def search_recipes(
        self,
        query: str,
        filters: Optional[Union[Dict[str, Any], RecipeSearchFilters]] = None,
        top_k: int = 5,
    ) -> List[ScoredRecipe]:
        return self._backend.search_recipes(query=query, filters=filters, top_k=top_k)


class _QdrantSearchBackend:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        recipes_by_id: Dict[str, RecipeRecord],
        settings: Settings,
    ) -> None:
        from qdrant_client import models

        self.embedding_service = embedding_service
        self.recipes_by_id = recipes_by_id
        self.settings = settings
        self.client = build_qdrant_client(settings)
        self.models = models
        collection = self._require_collection()
        sparse_vectors = collection.config.params.sparse_vectors or {}
        self._supports_sparse = (
            settings.qdrant_enable_sparse
            and (settings.qdrant_sparse_vector_name or DEFAULT_SPARSE_VECTOR_NAME) in sparse_vectors
        )
        self._sparse_vectorizer = SparseTextVectorizer()

    def search_recipes(
        self,
        query: str,
        filters: Optional[Union[Dict[str, Any], RecipeSearchFilters]] = None,
        top_k: int = 5,
    ) -> List[ScoredRecipe]:
        if top_k <= 0:
            return []

        normalized_filters = _normalize_filters(filters)
        query_filter = self._build_query_filter(normalized_filters)
        dense_vector = self.embedding_service.embed_text(query)
        dense_vector_name = self.settings.qdrant_dense_vector_name or DEFAULT_DENSE_VECTOR_NAME
        sparse_vector_name = self.settings.qdrant_sparse_vector_name or DEFAULT_SPARSE_VECTOR_NAME
        sparse_vector = self._build_sparse_query(query)
        search_params = self.models.SearchParams(hnsw_ef=QDRANT_HNSW_EF)

        if self._supports_sparse and sparse_vector is not None:
            prefetch_limit = max(top_k * 4, QDRANT_PREFETCH_LIMIT)
            response = self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                prefetch=[
                    self.models.Prefetch(
                        query=dense_vector,
                        using=dense_vector_name,
                        filter=query_filter,
                        params=search_params,
                        limit=prefetch_limit,
                    ),
                    self.models.Prefetch(
                        query=sparse_vector,
                        using=sparse_vector_name,
                        filter=query_filter,
                        limit=prefetch_limit,
                    ),
                ],
                query=self.models.FusionQuery(fusion=self.models.Fusion.RRF),
                limit=top_k,
                with_payload=["recipe_id"],
            )
            lexical_score = 1.0
        else:
            response = self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=dense_vector,
                using=dense_vector_name,
                query_filter=query_filter,
                search_params=search_params,
                limit=top_k,
                with_payload=["recipe_id"],
            )
            lexical_score = 0.0

        return self._to_scored_recipes(response.points, normalized_filters, lexical_score)

    def _build_query_filter(self, filters: RecipeSearchFilters):
        must: List[Any] = []
        must_not: List[Any] = []

        if filters.meal_type:
            must.append(
                self.models.FieldCondition(
                    key="meal_types",
                    match=self.models.MatchAny(any=[filters.meal_type]),
                )
            )
        if filters.cuisine:
            must.append(
                self.models.FieldCondition(
                    key="cuisine",
                    match=self.models.MatchValue(value=filters.cuisine.lower()),
                )
            )
        if filters.max_prep_time is not None:
            must.append(
                self.models.FieldCondition(
                    key="prep_time_min",
                    range=self.models.Range(lte=filters.max_prep_time),
                )
            )
        if filters.calorie_range:
            lower, upper = filters.calorie_range
            must.append(
                self.models.FieldCondition(
                    key="calories",
                    range=self.models.Range(gte=lower, lte=upper),
                )
            )
        for raw_tag in filters.dietary_tags:
            expected_tag = RESTRICTION_TAGS.get(raw_tag.lower())
            if expected_tag is None:
                continue
            must.append(
                self.models.FieldCondition(
                    key="dietary_restrictions",
                    match=self.models.MatchAny(any=[expected_tag]),
                )
            )
        for ingredient in filters.excluded_ingredients:
            normalized = " ".join(TOKEN_PATTERN.findall(ingredient.lower()))
            if not normalized:
                continue
            must_not.append(
                self.models.FieldCondition(
                    key="ingredient_text",
                    match=self.models.MatchText(text=normalized),
                )
            )

        if not must and not must_not:
            return None
        return self.models.Filter(must=must or None, must_not=must_not or None)

    def _build_sparse_query(self, query: str):
        indices, values = self._sparse_vectorizer.vectorize(query)
        if not indices:
            return None
        return self.models.SparseVector(indices=indices, values=values)

    def _to_scored_recipes(
        self,
        points: Sequence[Any],
        filters: RecipeSearchFilters,
        lexical_score: float,
    ) -> List[ScoredRecipe]:
        scored: List[ScoredRecipe] = []
        for point in points:
            payload = point.payload or {}
            recipe_id = payload.get("recipe_id")
            if recipe_id is None:
                continue
            recipe = self.recipes_by_id.get(recipe_id)
            if recipe is None:
                continue
            score = round(float(point.score), 4)
            scored.append(
                ScoredRecipe(
                    recipe=recipe,
                    score=score,
                    dense_score=score,
                    lexical_score=lexical_score,
                    rerank_score=score,
                    reasons=_score_reasons(recipe, filters),
                )
            )
        return scored

    def _require_collection(self):
        if not self.client.collection_exists(self.settings.qdrant_collection):
            raise RuntimeError(
                "Qdrant collection '{name}' was not found at '{url}'. Run scripts/seed_recipes.py first.".format(
                    name=self.settings.qdrant_collection,
                    url=self.settings.qdrant_url,
                )
            )
        return self.client.get_collection(self.settings.qdrant_collection)


class _InMemoryRecipeSearchBackend:
    def __init__(self, recipes: Sequence[RecipeRecord], embedding_service: EmbeddingService) -> None:
        self._recipes = list(recipes)
        self.embedding_service = embedding_service
        search_texts = [recipe_searchable_text(recipe) for recipe in self._recipes]
        embeddings = self.embedding_service.embed_texts(search_texts)
        self._embeddings = {
            recipe.recipe_id: embedding
            for recipe, embedding in zip(self._recipes, embeddings)
        }

    def search_recipes(
        self,
        query: str,
        filters: Optional[Union[Dict[str, Any], RecipeSearchFilters]] = None,
        top_k: int = 5,
    ) -> List[ScoredRecipe]:
        if top_k <= 0:
            return []

        normalized_filters = _normalize_filters(filters)
        query_embedding = self.embedding_service.embed_text(query)
        query_terms = set(TOKEN_PATTERN.findall(query.lower()))

        candidates: List[ScoredRecipe] = []
        for recipe in self._recipes:
            if not self._passes_filters(recipe, normalized_filters):
                continue

            searchable = recipe_searchable_text(recipe)
            lexical_score = self._lexical_score(query_terms, searchable)
            dense_score = self.embedding_service.cosine_similarity(
                query_embedding,
                self._embeddings[recipe.recipe_id],
            )
            metadata_score = self._metadata_score(query_terms, recipe)
            meal_type_bonus = self._meal_type_bonus(recipe, normalized_filters)
            combined_score = round(
                (dense_score * 0.55) + (lexical_score * 0.35) + (metadata_score * 0.10) + meal_type_bonus,
                4,
            )
            candidates.append(
                ScoredRecipe(
                    recipe=recipe,
                    score=combined_score,
                    dense_score=round(dense_score, 4),
                    lexical_score=round(lexical_score, 4),
                    rerank_score=combined_score,
                    reasons=_score_reasons(recipe, normalized_filters, metadata_score),
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:top_k]

    def _passes_filters(self, recipe: RecipeRecord, filters: RecipeSearchFilters) -> bool:
        payload = recipe_payload(recipe)
        dietary_restrictions = set(payload["dietary_restrictions"])
        ingredient_names = payload["ingredient_names"]

        if filters.meal_type and filters.meal_type not in recipe.meal_types:
            return False
        if filters.cuisine and recipe.cuisine.lower() != filters.cuisine.lower():
            return False
        if filters.max_prep_time is not None and recipe.prep_time_min > filters.max_prep_time:
            return False
        if filters.calorie_range:
            lower, upper = filters.calorie_range
            if recipe.calories < lower or recipe.calories > upper:
                return False
        for raw_tag in filters.dietary_tags:
            expected_tag = RESTRICTION_TAGS.get(raw_tag.lower())
            if expected_tag is None:
                continue
            if expected_tag not in dietary_restrictions:
                return False
        for ingredient in filters.excluded_ingredients:
            normalized = " ".join(TOKEN_PATTERN.findall(ingredient.lower()))
            if normalized and normalized in " ".join(ingredient_names):
                return False
        return True

    def _lexical_score(self, query_terms: Sequence[str], searchable: str) -> float:
        searchable_terms = set(TOKEN_PATTERN.findall(searchable.lower()))
        if not query_terms:
            return 0.0
        overlap = len(set(query_terms) & searchable_terms)
        return overlap / float(max(len(set(query_terms)), 1))

    def _metadata_score(self, query_terms: Iterable[str], recipe: RecipeRecord) -> float:
        bonus = 0.0
        lowered_terms = set(query_terms)
        lowered_tags = {tag.lower() for tag in recipe.tags}

        if "quick" in lowered_terms and recipe.prep_time_min <= 15:
            bonus += 0.7
        if "protein" in lowered_terms and recipe.protein_g >= 25:
            bonus += 0.7
        if "vegan" in lowered_terms and "vegan" in lowered_tags:
            bonus += 0.8
        if "vegetarian" in lowered_terms and "vegetarian" in lowered_tags:
            bonus += 0.8
        return min(1.0, bonus)

    def _meal_type_bonus(self, recipe: RecipeRecord, filters: RecipeSearchFilters) -> float:
        if not filters.meal_type:
            return 0.0
        if recipe.meal_types == [filters.meal_type]:
            return 0.08
        if recipe.meal_types and recipe.meal_types[0] == filters.meal_type:
            return 0.04
        return -0.02


def _normalize_filters(
    filters: Optional[Union[Dict[str, Any], RecipeSearchFilters]],
) -> RecipeSearchFilters:
    if isinstance(filters, RecipeSearchFilters):
        return filters
    if filters is None:
        return RecipeSearchFilters()
    return RecipeSearchFilters(
        meal_type=filters.get("meal_type"),
        cuisine=filters.get("cuisine"),
        max_prep_time=filters.get("max_prep_time"),
        dietary_tags=list(filters.get("dietary_tags", [])),
        calorie_range=tuple(filters["calorie_range"]) if filters.get("calorie_range") else None,
        excluded_ingredients=list(filters.get("excluded_ingredients", [])),
    )


def _score_reasons(
    recipe: RecipeRecord,
    filters: RecipeSearchFilters,
    metadata_score: float = 0.0,
) -> List[str]:
    reasons: List[str] = []
    if filters.meal_type and filters.meal_type in recipe.meal_types:
        reasons.append("meal-type match")
    if filters.max_prep_time is not None and recipe.prep_time_min <= filters.max_prep_time:
        reasons.append("prep-time match")
    if filters.dietary_tags:
        reasons.append("dietary tag match")
    if metadata_score >= 0.7:
        reasons.append("strong query-tag overlap")
    return reasons
