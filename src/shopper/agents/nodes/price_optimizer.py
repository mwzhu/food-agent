from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from shopper.agents.events import emit_run_event
from shopper.agents.llm import invoke_structured
from shopper.agents.tools.store_scraper import StoreAdapter, default_store_adapters
from shopper.schemas import ContextMetadata, GroceryItem, PurchaseOrder, StoreSummary
from shopper.services import (
    PricingSelection,
    build_purchase_orders,
    build_single_store_selection,
    build_split_selection,
    calculate_store_totals,
    check_budget,
    missing_priced_items,
    rank_by_price,
    total_order_cost,
)


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "price_tradeoff.md"


class TradeoffChoice(BaseModel):
    plan_id: str
    rationale: str


@dataclass(frozen=True)
class CandidatePurchasePlan:
    plan_id: str
    strategy: str
    rationale: str
    orders: list[PurchaseOrder]

    @property
    def total_cost(self) -> float:
        return total_order_cost(self.orders)

    @property
    def store_count(self) -> int:
        return len(self.orders)

    @property
    def online_order_count(self) -> int:
        return sum(1 for order in self.orders if order.channel == "online")


@dataclass
class PriceOptimizerNode:
    context_assembler: Optional[Any] = None
    chat_model: Optional[Any] = None
    store_adapters: Sequence[StoreAdapter] = field(default_factory=default_store_adapters)
    adapter_timeout_s: float = 3.0
    max_attempts: int = 2

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="planning",
            node_name="price_optimizer",
            message="Collecting store quotes in parallel and optimizing purchase orders against the weekly budget.",
        )

        grocery_list = self._consolidate_grocery_list([GroceryItem.model_validate(item) for item in state["grocery_list"]])
        budget = float(state["user_profile"]["budget_weekly"])
        priced_items = [item for item in grocery_list if not item.already_have and item.shopping_quantity > 0]

        if not priced_items:
            budget_summary = check_budget([], budget)
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
                phase="planning",
                node_name="price_optimizer",
                message="Every required ingredient is already in the fridge, so there is nothing left to price.",
                data={"grocery_item_count": len(grocery_list), "purchase_order_count": 0},
            )
            return {
                "grocery_list": [item.model_dump(mode="json") for item in grocery_list],
                "store_quotes": [],
                "store_summaries": [],
                "purchase_orders": [],
                "budget_summary": budget_summary.model_dump(mode="json"),
                "replan_reason": None,
                "price_strategy": "fridge_only",
                "price_rationale": "All required ingredients are already available at home.",
                "context_metadata": [metadata.model_dump(mode="json")],
            }

        quote_map, adapter_failures = await self._collect_quotes(priced_items)
        ranked_items = rank_by_price(grocery_list, quote_map)
        store_summaries = calculate_store_totals(ranked_items, quote_map)
        candidate_plans = self._build_candidate_plans(ranked_items, quote_map, store_summaries)
        chosen_plan, llm_rationale, metadata = await self._choose_plan(
            state=state,
            ranked_items=ranked_items,
            store_summaries=store_summaries,
            candidate_plans=candidate_plans,
            adapter_failures=adapter_failures,
        )

        purchase_orders = chosen_plan.orders if chosen_plan is not None else []
        budget_summary = check_budget(purchase_orders, budget)
        final_grocery_list = self._apply_selected_orders(ranked_items, purchase_orders, quote_map)

        replan_reason = self._build_replan_reason(
            ranked_items=ranked_items,
            purchase_orders=purchase_orders,
            budget_summary=budget_summary,
            adapter_failures=adapter_failures,
        )
        price_strategy = chosen_plan.strategy if chosen_plan is not None else "no_viable_plan"
        rationale_parts = [part for part in [chosen_plan.rationale if chosen_plan is not None else None, llm_rationale] if part]
        if adapter_failures:
            rationale_parts.append(
                "Pricing proceeded with partial store coverage after: {failures}.".format(
                    failures=", ".join(adapter_failures)
                )
            )
        price_rationale = " ".join(rationale_parts) if rationale_parts else "Selected the lowest-cost viable store strategy."

        await emit_run_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="planning",
            node_name="price_optimizer",
            message=(
                "Optimized {order_count} purchase orders using the {strategy} strategy."
                if chosen_plan is not None
                else "Could not build a complete purchase plan from the available store quotes."
            ).format(
                order_count=len(purchase_orders),
                strategy=price_strategy.replace("_", " "),
            ),
            data={
                "purchase_order_count": len(purchase_orders),
                "store_count": len(store_summaries),
                "within_budget": budget_summary.within_budget,
                "total_cost": budget_summary.total_cost,
                "strategy": price_strategy,
                "adapter_failures": adapter_failures,
            },
        )

        return {
            "grocery_list": [item.model_dump(mode="json") for item in final_grocery_list],
            "store_quotes": [
                quote.model_dump(mode="json")
                for store_quotes in quote_map.values()
                for quote in store_quotes
            ],
            "store_summaries": [summary.model_dump(mode="json") for summary in store_summaries],
            "purchase_orders": [order.model_dump(mode="json") for order in purchase_orders],
            "budget_summary": budget_summary.model_dump(mode="json"),
            "replan_reason": replan_reason,
            "price_strategy": price_strategy,
            "price_rationale": price_rationale,
            "context_metadata": [metadata.model_dump(mode="json")],
        }

    async def _collect_quotes(
        self,
        items: Sequence[GroceryItem],
    ) -> tuple[dict[str, list[Any]], list[str]]:
        async def run_adapter(adapter: StoreAdapter):
            return adapter.store_name, await self._search_with_retry(adapter, items)

        results = await asyncio.gather(*(run_adapter(adapter) for adapter in self.store_adapters), return_exceptions=True)
        quote_map: dict[str, list[Any]] = {}
        failures: list[str] = []

        for result in results:
            if isinstance(result, Exception):
                failures.append(str(result))
                continue
            store_name, quotes = result
            quote_map[store_name] = quotes

        return quote_map, failures

    async def _search_with_retry(
        self,
        adapter: StoreAdapter,
        items: Sequence[GroceryItem],
    ) -> list[Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await asyncio.wait_for(adapter.search_prices(items), timeout=self.adapter_timeout_s)
            except Exception as exc:  # pragma: no cover - failure path exercised in unit tests
                last_error = exc
                if attempt == self.max_attempts:
                    break
                await asyncio.sleep(0.08 * attempt)

        assert last_error is not None
        raise RuntimeError(
            "Store adapter {store} failed after {attempts} attempts: {message}".format(
                store=adapter.store_name,
                attempts=self.max_attempts,
                message=str(last_error),
            )
        ) from last_error

    def _build_candidate_plans(
        self,
        ranked_items: Sequence[GroceryItem],
        quote_map: Dict[str, Sequence[Any]],
        store_summaries: Sequence[StoreSummary],
    ) -> list[CandidatePurchasePlan]:
        plans: list[CandidatePurchasePlan] = []

        split_selection = build_split_selection(ranked_items)
        split_online = self._build_plan(
            "split_online",
            "split_delivery",
            "Split the basket across the cheapest available stores and keep delivery enabled.",
            ranked_items,
            quote_map,
            split_selection,
        )
        if split_online is not None:
            plans.append(split_online)

        if split_selection.channels_by_store:
            split_in_store_selection = PricingSelection(
                item_store_map=dict(split_selection.item_store_map),
                channels_by_store={store: "in_store" for store in split_selection.channels_by_store},
            )
            split_in_store = self._build_plan(
                "split_in_store",
                "split_pickup",
                "Split the basket across the cheapest stores but avoid delivery fees by shopping in store.",
                ranked_items,
                quote_map,
                split_in_store_selection,
            )
            if split_in_store is not None:
                plans.append(split_in_store)

        for summary in store_summaries:
            if not summary.all_items_available:
                continue
            single_store_selection = build_single_store_selection(ranked_items, summary.store)
            single_store_online = self._build_plan(
                f"{summary.store.lower()}_online",
                "single_store_delivery",
                "Keep everything at {store} for a simpler one-store order.".format(store=summary.store),
                ranked_items,
                quote_map,
                single_store_selection,
            )
            if single_store_online is not None:
                plans.append(single_store_online)

            single_store_in_store = self._build_plan(
                f"{summary.store.lower()}_in_store",
                "single_store_in_store",
                "Keep everything at {store} and avoid delivery fees with an in-store trip.".format(store=summary.store),
                ranked_items,
                quote_map,
                PricingSelection(
                    item_store_map=dict(single_store_selection.item_store_map),
                    channels_by_store={summary.store: "in_store"},
                ),
            )
            if single_store_in_store is not None:
                plans.append(single_store_in_store)

        deduped: dict[str, CandidatePurchasePlan] = {}
        for plan in plans:
            deduped[plan.plan_id] = plan
        return list(deduped.values())

    def _build_plan(
        self,
        plan_id: str,
        strategy: str,
        rationale: str,
        ranked_items: Sequence[GroceryItem],
        quote_map: Dict[str, Sequence[Any]],
        selection: PricingSelection,
    ) -> Optional[CandidatePurchasePlan]:
        orders = build_purchase_orders(ranked_items, quote_map, selection)
        if missing_priced_items(ranked_items, orders):
            return None
        return CandidatePurchasePlan(plan_id=plan_id, strategy=strategy, rationale=rationale, orders=orders)

    async def _choose_plan(
        self,
        *,
        state: Dict[str, Any],
        ranked_items: Sequence[GroceryItem],
        store_summaries: Sequence[StoreSummary],
        candidate_plans: Sequence[CandidatePurchasePlan],
        adapter_failures: Sequence[str],
    ) -> tuple[Optional[CandidatePurchasePlan], Optional[str], ContextMetadata]:
        budget = float(state["user_profile"]["budget_weekly"])
        affordable_plan_ids = {
            plan.plan_id
            for plan in candidate_plans
            if check_budget(plan.orders, budget).within_budget
        }
        heuristic_choice = self._heuristic_plan_choice(state["user_profile"].get("schedule_json", {}), candidate_plans, budget)
        llm_rationale: Optional[str] = None

        if not candidate_plans:
            return (
                None,
                None,
                ContextMetadata(
                    node_name="price_optimizer",
                    tokens_used=0,
                    token_budget=0,
                    fields_included=["grocery_list", "store_summaries"],
                    fields_dropped=[],
                    retrieved_memory_ids=[],
                ),
            )

        context_metadata = ContextMetadata(
            node_name="price_optimizer",
            tokens_used=0,
            token_budget=0,
            fields_included=["grocery_list", "store_summaries"],
            fields_dropped=[],
            retrieved_memory_ids=[],
        )
        context_payload = {
            "user_profile_summary": {
                "budget_weekly": state["user_profile"]["budget_weekly"],
                "cooking_skill": state["user_profile"]["cooking_skill"],
                "goal": state["user_profile"]["goal"],
            },
            "schedule": state["user_profile"]["schedule_json"],
            "grocery_list": [
                {
                    "name": item.name,
                    "quantity": item.shopping_quantity,
                    "unit": item.unit,
                    "category": item.category,
                }
                for item in ranked_items
                if not item.already_have and item.shopping_quantity > 0
            ],
            "store_summaries": [summary.model_dump(mode="json") for summary in store_summaries],
        }
        if self.context_assembler is not None:
            context = await self.context_assembler.build_context(
                "price_optimizer",
                {
                    **state,
                    "grocery_list": [item.model_dump(mode="json") for item in ranked_items],
                    "store_summaries": [summary.model_dump(mode="json") for summary in store_summaries],
                },
            )
            context_payload = context.payload
            context_metadata = ContextMetadata(
                node_name="price_optimizer",
                tokens_used=context.budget.tokens_used,
                token_budget=context.budget.token_budget,
                fields_included=context.budget.fields_included,
                fields_dropped=context.budget.fields_dropped,
                retrieved_memory_ids=[],
            )

        llm_choice = await self._llm_plan_choice(
            context_payload=context_payload,
            candidate_plans=candidate_plans,
            affordable_plan_ids=affordable_plan_ids,
            adapter_failures=adapter_failures,
        )
        if llm_choice is not None:
            llm_rationale = llm_choice.rationale
            selected = next((plan for plan in candidate_plans if plan.plan_id == llm_choice.plan_id), None)
            if selected is not None:
                if affordable_plan_ids and selected.plan_id not in affordable_plan_ids:
                    selected = min(
                        (plan for plan in candidate_plans if plan.plan_id in affordable_plan_ids),
                        key=lambda plan: (plan.total_cost, plan.store_count),
                    )
                    llm_rationale = (
                        "{rationale} A deterministic budget guard switched to the lowest-cost plan that stays within budget."
                    ).format(rationale=llm_choice.rationale)
                return selected, llm_rationale, context_metadata

        return heuristic_choice, llm_rationale, context_metadata

    async def _llm_plan_choice(
        self,
        *,
        context_payload: Dict[str, Any],
        candidate_plans: Sequence[CandidatePurchasePlan],
        affordable_plan_ids: set[str],
        adapter_failures: Sequence[str],
    ) -> Optional[TradeoffChoice]:
        if self.chat_model is None or not candidate_plans:
            return None

        prompt_template = PROMPT_PATH.read_text(encoding="utf-8").strip()
        evidence = {
            "context": context_payload,
            "candidates": [
                {
                    "plan_id": plan.plan_id,
                    "strategy": plan.strategy,
                    "rationale": plan.rationale,
                    "store_count": plan.store_count,
                    "online_order_count": plan.online_order_count,
                    "total_cost": plan.total_cost,
                    "orders": [order.model_dump(mode="json") for order in plan.orders],
                    "within_budget": plan.plan_id in affordable_plan_ids,
                }
                for plan in candidate_plans
            ],
            "adapter_failures": list(adapter_failures),
        }
        return await invoke_structured(
            self.chat_model,
            TradeoffChoice,
            [
                SystemMessage(content=prompt_template),
                HumanMessage(content=json.dumps(evidence, indent=2, ensure_ascii=True)),
            ],
        )

    def _heuristic_plan_choice(
        self,
        schedule_json: Dict[str, str],
        candidate_plans: Sequence[CandidatePurchasePlan],
        budget: float,
    ) -> Optional[CandidatePurchasePlan]:
        if not candidate_plans:
            return None

        affordable = [plan for plan in candidate_plans if check_budget(plan.orders, budget).within_budget]
        pool = affordable or list(candidate_plans)
        min_total = min(plan.total_cost for plan in pool)
        contenders = [plan for plan in pool if plan.total_cost <= min_total + 6.0]

        schedule_text = " ".join(str(value).lower() for value in schedule_json.values())
        time_constrained = any(keyword in schedule_text for keyword in ("quick", "busy", "15", "20", "30"))

        if time_constrained:
            contenders.sort(key=lambda plan: (0 if plan.online_order_count else 1, plan.store_count, plan.total_cost))
        else:
            contenders.sort(key=lambda plan: (plan.store_count, plan.total_cost, 0 if plan.online_order_count == 0 else 1))

        return contenders[0]

    def _apply_selected_orders(
        self,
        ranked_items: Sequence[GroceryItem],
        purchase_orders: Sequence[PurchaseOrder],
        quote_map: Dict[str, Sequence[Any]],
    ) -> list[GroceryItem]:
        order_lookup = {
            self._item_key(order_item.name, order_item.unit, order_item.quantity): (order.store, order.channel, order_item.price)
            for order in purchase_orders
            for order_item in order.items
        }
        quote_lookup = {
            (store, self._item_key(quote.item_name, quote.requested_unit, quote.requested_quantity)): quote
            for store, quotes in quote_map.items()
            for quote in quotes
        }
        final_items: list[GroceryItem] = []
        for item in ranked_items:
            item_key = self._item_key(item.name, item.unit, item.shopping_quantity if item.shopping_quantity > 0 else item.quantity)
            selected = order_lookup.get(item_key)
            if selected is None:
                final_items.append(item.model_copy(update={"buy_online": None}))
                continue

            store, channel, price = selected
            selected_quote = quote_lookup.get((store, item_key))
            final_items.append(
                item.model_copy(
                    update={
                        "best_store": store,
                        "best_price": price if selected_quote is None else round(selected_quote.price, 2),
                        "buy_online": channel == "online",
                    }
                )
            )
        return final_items

    def _build_replan_reason(
        self,
        *,
        ranked_items: Sequence[GroceryItem],
        purchase_orders: Sequence[PurchaseOrder],
        budget_summary,
        adapter_failures: Sequence[str],
    ) -> Optional[str]:
        missing_items = missing_priced_items(ranked_items, purchase_orders)
        reasons: list[str] = []

        if missing_items:
            reasons.append(
                "Some ingredients were unavailable across the remaining stores: {items}.".format(
                    items=", ".join(missing_items)
                )
            )
        if not budget_summary.within_budget:
            reasons.append(
                "The cheapest complete basket still lands {overage:.2f} over the weekly budget.".format(
                    overage=budget_summary.overage
                )
            )
        if adapter_failures:
            reasons.append(
                "At least one store adapter failed while quoting prices, so optimization used partial coverage."
            )

        return " ".join(reasons) if reasons else None

    def _consolidate_grocery_list(self, items: Sequence[GroceryItem]) -> list[GroceryItem]:
        grouped: dict[tuple[str, str | None, str, bool], GroceryItem] = {}

        for item in items:
            key = (item.name.lower().strip(), item.unit, item.category, item.already_have)
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = item
                continue

            grouped[key] = existing.model_copy(
                update={
                    "quantity": round(existing.quantity + item.quantity, 2),
                    "shopping_quantity": round(existing.shopping_quantity + item.shopping_quantity, 2),
                    "quantity_in_fridge": round(existing.quantity_in_fridge + item.quantity_in_fridge, 2),
                    "source_recipe_ids": list(dict.fromkeys([*existing.source_recipe_ids, *item.source_recipe_ids])),
                }
            )

        return sorted(grouped.values(), key=lambda item: (item.category, item.name))

    def _item_key(self, name: str, unit: Optional[str], quantity: float) -> str:
        return "{name}|{unit}|{quantity}".format(
            name=name.lower().strip(),
            unit=(unit or "").lower(),
            quantity=round(quantity, 2),
        )
