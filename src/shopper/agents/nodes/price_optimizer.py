from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from shopper.agents.events import emit_run_event
from shopper.schemas import ContextMetadata


@dataclass
class PriceOptimizerNode:
    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="shopping",
            node_name="price_optimizer",
            message="Price optimization is stubbed for Phase 3, so the grocery list is passing through unchanged.",
        )

        grocery_list = state["grocery_list"]
        metadata = ContextMetadata(
            node_name="price_optimizer",
            tokens_used=0,
            token_budget=0,
            fields_included=["grocery_list"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="shopping",
            node_name="price_optimizer",
            message="Skipped store-level optimization and kept the grocery list intact.",
            data={"grocery_item_count": len(grocery_list)},
        )

        return {
            "grocery_list": grocery_list,
            "fridge_inventory": state["fridge_inventory"],
            "context_metadata": [metadata.model_dump(mode="json")],
        }
