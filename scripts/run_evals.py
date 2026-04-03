from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shopper.agents import build_planner_graph  # noqa: E402
from shopper.config import get_settings  # noqa: E402
from shopper.evaluation import EvaluationRunner  # noqa: E402
from shopper.memory import ContextAssembler, MemoryStore  # noqa: E402
from shopper.retrieval import QdrantRecipeStore  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Shopper evaluation suites.")
    parser.add_argument(
        "--eval",
        required=True,
        help=(
            "Single eval name or a comma-separated list: "
            "nutrition,daily_macro_alignment,meal_relevance,safety,groundedness,"
            "grocery_completeness,grocery_aggregation,grocery_fridge_diff,grocery_traceability,grocery_category"
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    memory_store = MemoryStore()
    context_assembler = ContextAssembler(memory_store=memory_store)
    recipe_store = QdrantRecipeStore(ROOT / settings.recipe_corpus_path)
    graph = build_planner_graph(
        context_assembler=context_assembler,
        memory_store=memory_store,
        recipe_store=recipe_store,
        session_factory=memory_store.session_factory,
    )
    runner = EvaluationRunner(graph=graph, settings=settings, recipe_store=recipe_store)

    eval_names = [name.strip() for name in args.eval.split(",") if name.strip()]
    summaries = [await runner.run(eval_name) for eval_name in eval_names]
    payload = summaries[0] if len(summaries) == 1 else {"passed": all(item["passed"] for item in summaries), "summaries": summaries}
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
