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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Shopper evaluation suites.")
    parser.add_argument("--eval", required=True, choices=["nutrition"])
    args = parser.parse_args()

    settings = get_settings()
    memory_store = MemoryStore()
    context_assembler = ContextAssembler(memory_store=memory_store)
    graph = build_planner_graph(context_assembler=context_assembler)
    runner = EvaluationRunner(graph=graph, settings=settings)

    summary = await runner.run(args.eval)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
