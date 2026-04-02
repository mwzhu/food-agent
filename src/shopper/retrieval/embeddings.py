from __future__ import annotations

import hashlib
import math
import re
from typing import List, Optional, Sequence

from shopper.config import Settings, get_settings


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingService:
    """OpenAI embeddings with a deterministic local fallback."""

    def __init__(self, dimensions: int = 64, settings: Optional[Settings] = None) -> None:
        self.dimensions = dimensions
        self.settings = settings or get_settings()
        self._openai_embeddings = None

    def embed_text(self, text: str) -> List[float]:
        if self._should_use_openai():
            embeddings = self._get_openai_embeddings()
            if embeddings is not None:
                try:
                    return list(embeddings.embed_query(text))
                except Exception:
                    pass
        return self._local_embed(text)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        if self._should_use_openai():
            embeddings = self._get_openai_embeddings()
            if embeddings is not None:
                try:
                    return [list(vector) for vector in embeddings.embed_documents(text_list)]
                except Exception:
                    pass
        return [self._local_embed(text) for text in text_list]

    def cosine_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right:
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    def _should_use_openai(self) -> bool:
        return (
            self.settings.app_env != "test"
            and self.settings.embedding_provider == "openai"
            and bool(self.settings.openai_api_key)
        )

    def _get_openai_embeddings(self):
        if self._openai_embeddings is not None:
            return self._openai_embeddings

        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            return None

        self._openai_embeddings = OpenAIEmbeddings(
            model=self.settings.embedding_model,
            api_key=self.settings.openai_api_key,
        )
        return self._openai_embeddings

    def _local_embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % self.dimensions
            sign = 1.0 if int(digest[8:16], 16) % 2 == 0 else -1.0
            vector[bucket] += sign

        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]
