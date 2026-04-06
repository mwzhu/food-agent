from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from shopper.agents.events import emit_run_event
from shopper.schemas import ContextMetadata, FridgeItemSnapshot, GroceryItem, MealSlot
from shopper.services import aggregate_quantities, categorize, diff_against_fridge, extract_ingredients
from shopper.validators import (
    validate_fridge_inventory_consistency,
    validate_grocery_aggregation,
    validate_grocery_fridge_diff,
    validate_grocery_list,
    validate_grocery_traceability,
)


@dataclass
class GroceryBuilderNode:
    get_fridge_contents_tool: Any

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="shopping",
            node_name="grocery_builder",
            message="Aggregating recipe ingredients and diffing them against the fridge.",
        )

        meals = [MealSlot.model_validate(item) for item in state["selected_meals"]]
        if state.get("fridge_inventory"):
            fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in state["fridge_inventory"]]
        else:
            fridge_payload = await self.get_fridge_contents_tool.ainvoke({"user_id": state["user_id"]})
            fridge_inventory = [FridgeItemSnapshot.model_validate(item) for item in fridge_payload]
        grocery_list = categorize(
            diff_against_fridge(
                aggregate_quantities(extract_ingredients(meals)),
                fridge_inventory,
            )
        )
        self._validate_grocery_outputs(meals, grocery_list, fridge_inventory)

        metadata = ContextMetadata(
            node_name="grocery_builder",
            tokens_used=0,
            token_budget=0,
            fields_included=["selected_meals", "fridge_inventory"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="shopping",
            node_name="grocery_builder",
            message="Built a grocery list with {count} tracked items.".format(count=len(grocery_list)),
            data={
                "grocery_item_count": len(grocery_list),
                "already_have_count": sum(1 for item in grocery_list if item.already_have),
            },
        )

        return {
            "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
            "fridge_inventory": [item.model_dump(mode="json") for item in fridge_inventory],
            "context_metadata": [metadata.model_dump(mode="json")],
        }

    def _validate_grocery_outputs(
        self,
        meals: list[MealSlot],
        grocery_list: list[GroceryItem],
        fridge_inventory: list[FridgeItemSnapshot],
    ) -> None:
        issues = (
            validate_grocery_list(meals, grocery_list)
            + validate_grocery_aggregation(meals, grocery_list)
            + validate_grocery_fridge_diff(meals, grocery_list, fridge_inventory)
            + validate_fridge_inventory_consistency(grocery_list, fridge_inventory)
            + validate_grocery_traceability(meals, grocery_list)
        )
        if issues:
            raise ValueError(
                "Grocery builder produced an invalid shopping list: {issues}".format(
                    issues="; ".join(issues)
                )
            )
