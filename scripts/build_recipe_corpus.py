from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.retrieval.corpus_builder import build_recipe_corpus  # noqa: E402


def main() -> int:
    source_path = ROOT / "data/recipes/full_dataset.csv"
    output_path = ROOT / "data/recipes/phase2_recipe_corpus.json"
    curated_seed_path = ROOT / "data/recipes/curated_recipe_seed.json"
    summary = build_recipe_corpus(
        source_path=source_path,
        output_path=output_path,
        curated_seed_path=curated_seed_path,
        target_count=2000,
    )
    print(json.dumps(summary.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
