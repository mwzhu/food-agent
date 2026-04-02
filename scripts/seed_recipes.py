from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.config import get_settings  # noqa: E402
from shopper.retrieval.seed import seed_recipe_collection  # noqa: E402


def main() -> int:
    settings = get_settings()
    result = seed_recipe_collection(settings.recipe_corpus_path, settings=settings)
    print(
        json.dumps(
            {
                "recipe_count": result.recipe_count,
                "batch_count": result.batch_count,
                "vector_size": result.vector_size,
                "collection_name": result.collection_name,
                "qdrant_url": settings.qdrant_url,
                "sparse_enabled": result.sparse_enabled,
                "corpus_path": settings.recipe_corpus_path,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
