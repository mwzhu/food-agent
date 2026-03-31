from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopper.graph.state import RunState
from shopper.integrations.browser import BrowserExecutor, BrowserSession
from shopper.memory.base import BaseMemoryStore
from shopper.memory.context import ContextAssembler
from shopper.models import AuditLogModel, FeedbackModel, IntegrationSessionModel, RunModel, UserProfileModel
from shopper.schemas import (
    ApprovalRequest,
    BasketPlan,
    FeedbackRequest,
    GroceryDemandItem,
    MemoryEvent,
    MealPlan,
    PantryItem,
    ProfileFacts,
    ResumeRequest,
    RunInput,
    RunResponse,
    VerifierResult,
)
from shopper.services.grocery import derive_grocery_demand
from shopper.services.nutrition import calculate_nutrition_targets
from shopper.services.planning import RECIPE_FIXTURES, RecipeRetriever, select_weekly_meal_plan
from shopper.services.pricing import QuoteAdapter, build_basket_plan
from shopper.services.verifier import verify_basket_against_budget, verify_cart_snapshot

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - handled during runtime if package missing
    END = "__end__"
    StateGraph = None


@dataclass
class AppServices:
    memory_store: BaseMemoryStore
    context_assembler: ContextAssembler
    recipe_retriever: RecipeRetriever
    quote_adapters: list[QuoteAdapter]
    browser_executor: BrowserExecutor


class RunOrchestrator:
    def __init__(self, services: AppServices) -> None:
        self.services = services

    async def _write_audit(self, session: AsyncSession, run_id: str, stage: str, action: str, details: dict) -> None:
        session.add(AuditLogModel(run_id=run_id, stage=stage, action=action, details=details))

    def _build_graph(self):
        if StateGraph is None:
            raise RuntimeError("langgraph is required to execute the orchestration graph")

        graph = StateGraph(RunState)

        def normalize_request(state: RunState) -> RunState:
            state["current_stage"] = "normalize_request"
            return state

        def load_memory(state: RunState) -> RunState:
            state["current_stage"] = "load_memory"
            return state

        def planning_subgraph(state: RunState) -> RunState:
            profile = ProfileFacts.model_validate(state["profile"])
            nutrition_targets = calculate_nutrition_targets(profile)
            memories = state.get("episodic_memory", [])
            candidates = self.services.recipe_retriever.search(profile)
            planning_context = self.services.context_assembler.build_planning_context(
                profile=profile,
                nutrition_targets=nutrition_targets,
                schedule_summary=state["schedule_summary"],
                pantry_snapshot=state["pantry_snapshot"],
                relevant_memories=memories,
                candidate_recipe_names=[recipe.name for recipe in candidates],
            )
            meal_plan = select_weekly_meal_plan(profile, candidates, memories)
            state["nutrition_targets"] = nutrition_targets.model_dump()
            state["candidate_recipes"] = [recipe.model_dump() for recipe in candidates]
            state["meal_plan"] = meal_plan.model_dump()
            state.setdefault("context_logs", []).append(
                {"stage": "planning", "included_keys": planning_context.included_keys, "token_budget": planning_context.token_budget}
            )
            state["current_stage"] = "planning_subgraph"
            return state

        def planning_critic(state: RunState) -> RunState:
            meal_plan_names = " ".join(recipe["name"].lower() for recipe in state.get("meal_plan", {}).get("recipes", []))
            allergies = {item.lower() for item in state["profile"].get("allergies", [])}
            passed = not any(allergy in meal_plan_names for allergy in allergies)
            result = VerifierResult(
                stage="planning_critic",
                passed=passed,
                message="Meal plan passed allergy check." if passed else "Meal plan conflicts with allergy constraints.",
                details={"allergies": list(allergies)},
            )
            state.setdefault("verifier_results", []).append(result.model_dump())
            state["current_stage"] = "planning_critic"
            if not passed:
                state["status"] = "failed"
                state["error_message"] = result.message
            return state

        def shopping_subgraph(state: RunState) -> RunState:
            profile = ProfileFacts.model_validate(state["profile"])
            meal_plan = MealPlan.model_validate(state["meal_plan"])
            grocery = derive_grocery_demand(
                meal_plan=meal_plan,
                pantry_snapshot=[PantryItem.model_validate(item) for item in state["pantry_snapshot"]],
            )
            shopping_context = self.services.context_assembler.build_shopping_context(
                meal_plan=meal_plan,
                grocery_demand=[item.model_dump() for item in grocery],
                budget_weekly=state["budget_weekly"],
                preferred_stores=profile.preferred_stores,
                relevant_memories=state.get("episodic_memory", []),
            )
            state.setdefault("context_logs", []).append(
                {"stage": "shopping", "included_keys": shopping_context.included_keys, "token_budget": shopping_context.token_budget}
            )
            state["grocery_demand"] = [item.model_dump() for item in grocery]
            state["current_stage"] = "shopping_subgraph"
            return state

        async def shopping_critic(state: RunState) -> RunState:
            grocery = [GroceryDemandItem.model_validate(item) for item in state["grocery_demand"]]
            quotes = []
            for adapter in self.services.quote_adapters:
                quotes.extend((await adapter.quote_items(grocery)))
            basket = build_basket_plan(grocery, quotes, state["profile"].get("preferred_stores", ["walmart"]))
            budget_result = verify_basket_against_budget(basket, state["budget_weekly"])
            state["quotes"] = [quote.model_dump() for quote in quotes]
            state["basket_plan"] = basket.model_dump()
            state.setdefault("verifier_results", []).append(budget_result.model_dump())
            state["current_stage"] = "shopping_critic"
            if not budget_result.passed:
                state["status"] = "manual_review"
            return state

        async def execution_subgraph(state: RunState) -> RunState:
            basket_plan = BasketPlan.model_validate(state["basket_plan"])
            session = BrowserSession(profile_id=state["trace_metadata"].get("profile_id", "local-profile"))
            restored = await self.services.browser_executor.restore_session(session)
            cart = await self.services.browser_executor.build_cart(session, basket_plan)
            state["browser_state"] = {"restored": restored, "cart": cart}
            state["current_stage"] = "execution_subgraph"
            return state

        def execution_verifier(state: RunState) -> RunState:
            basket = BasketPlan.model_validate(state["basket_plan"])
            cart_result = verify_cart_snapshot(state["browser_state"]["cart"], basket)
            state.setdefault("verifier_results", []).append(cart_result.model_dump())
            if not cart_result.passed:
                state["status"] = "manual_review"
                state["pending_interrupt"] = None
            elif state.get("approval_required", True):
                state["status"] = "awaiting_approval"
                state["pending_interrupt"] = ApprovalRequest(
                    run_id=state["run_id"],
                    reason="Approval required before irreversible checkout.",
                    basket_plan=basket,
                ).model_dump()
            else:
                state["status"] = "ready_for_checkout"
            state["current_stage"] = "execution_verifier"
            return state

        graph.add_node("normalize_request", normalize_request)
        graph.add_node("load_memory", load_memory)
        graph.add_node("planning_subgraph", planning_subgraph)
        graph.add_node("planning_critic", planning_critic)
        graph.add_node("shopping_subgraph", shopping_subgraph)
        graph.add_node("shopping_critic", shopping_critic)
        graph.add_node("execution_subgraph", execution_subgraph)
        graph.add_node("execution_verifier", execution_verifier)
        graph.set_entry_point("normalize_request")
        graph.add_edge("normalize_request", "load_memory")
        graph.add_edge("load_memory", "planning_subgraph")
        graph.add_edge("planning_subgraph", "planning_critic")
        graph.add_edge("planning_critic", "shopping_subgraph")
        graph.add_edge("shopping_subgraph", "shopping_critic")
        graph.add_edge("shopping_critic", "execution_subgraph")
        graph.add_edge("execution_subgraph", "execution_verifier")
        graph.add_edge("execution_verifier", END)
        return graph.compile()

    async def start_run(self, session: AsyncSession, run_input: RunInput) -> RunResponse:
        profile = run_input.profile
        user = await session.get(UserProfileModel, run_input.user_id)
        if user is None:
            user = UserProfileModel(user_id=run_input.user_id)
            session.add(user)
        user.canonical_facts = profile.model_dump()

        preference_summary = await self.services.memory_store.distill(run_input.user_id)
        user.preference_summary = preference_summary.model_dump(mode="json")

        episodic_matches = await self.services.memory_store.search(
            run_input.user_id,
            "meal_feedback",
            query=f"{profile.goal} {' '.join(profile.dislikes)} {' '.join(profile.dietary_restrictions)}",
            limit=5,
        )
        run_id = str(uuid4())
        state: RunState = {
            "run_id": run_id,
            "user_id": run_input.user_id,
            "profile": profile.model_dump(),
            "budget_weekly": run_input.budget_weekly,
            "schedule_summary": run_input.schedule_summary,
            "pantry_snapshot": [item.model_dump() for item in run_input.pantry_snapshot],
            "approval_required": run_input.require_approval,
            "canonical_memory": jsonable_encoder(user.preference_summary),
            "episodic_memory": [event.content for event in episodic_matches],
            "context_logs": [],
            "verifier_results": [],
            "status": "running",
            "current_stage": "created",
            "trace_metadata": {"profile_id": "local-profile", "langsmith_project": "shopper"},
            "pending_interrupt": None,
            "error_message": None,
        }

        graph = self._build_graph()
        result = await graph.ainvoke(state)
        run_model = RunModel(
            run_id=run_id,
            user_id=run_input.user_id,
            status=result["status"],
            current_stage=result["current_stage"],
            graph_state=jsonable_encoder(result),
            artifacts=jsonable_encoder({
                "nutrition_targets": result.get("nutrition_targets"),
                "meal_plan": result.get("meal_plan"),
                "grocery_demand": result.get("grocery_demand"),
                "basket_plan": result.get("basket_plan"),
                "context_logs": result.get("context_logs", []),
            }),
            pending_interrupt=jsonable_encoder(result.get("pending_interrupt")),
            verifier_results=jsonable_encoder(result.get("verifier_results", [])),
            trace_metadata=jsonable_encoder(result.get("trace_metadata", {})),
            error_message=result.get("error_message"),
        )
        session.add(run_model)
        await self._write_audit(session, run_id, result["current_stage"], "run_created", {"status": result["status"]})
        await session.commit()
        return RunResponse(
            run_id=run_id,
            status=result["status"],
            current_stage=result["current_stage"],
            artifacts=run_model.artifacts,
            pending_interrupt=run_model.pending_interrupt,
            verifier_results=[VerifierResult.model_validate(item) for item in run_model.verifier_results],
            trace_metadata=run_model.trace_metadata,
        )

    async def get_run(self, session: AsyncSession, run_id: str) -> RunResponse:
        run = await session.get(RunModel, run_id)
        if run is None:
            raise LookupError(run_id)
        return RunResponse(
            run_id=run.run_id,
            status=run.status,
            current_stage=run.current_stage,
            artifacts=run.artifacts,
            pending_interrupt=run.pending_interrupt,
            verifier_results=[VerifierResult.model_validate(item) for item in run.verifier_results],
            trace_metadata=run.trace_metadata,
        )

    async def resume_run(self, session: AsyncSession, run_id: str, request: ResumeRequest) -> RunResponse:
        run = await session.get(RunModel, run_id)
        if run is None:
            raise LookupError(run_id)

        basket = BasketPlan.model_validate(run.artifacts["basket_plan"])
        session_info = await session.execute(
            select(IntegrationSessionModel).where(
                IntegrationSessionModel.user_id == run.user_id,
                IntegrationSessionModel.provider == "walmart",
            )
        )
        integration = session_info.scalar_one_or_none()
        profile_id = integration.profile_id if integration else "local-profile"

        if not request.approved:
            run.status = "manual_review"
            run.current_stage = "approval_rejected"
            run.pending_interrupt = None
            await self._write_audit(session, run_id, "approval", "rejected", {"notes": request.human_edit.model_dump() if request.human_edit else {}})
        else:
            checkout_result = await self.services.browser_executor.complete_checkout(
                BrowserSession(profile_id=profile_id),
                basket,
            )
            run.status = checkout_result.status
            run.current_stage = "checkout_completed"
            run.pending_interrupt = None
            run.artifacts["checkout_result"] = checkout_result.model_dump()
            await self._write_audit(session, run_id, "checkout", "completed", checkout_result.model_dump())

        await session.commit()
        return await self.get_run(session, run_id)

    async def record_feedback(self, session: AsyncSession, request: FeedbackRequest) -> None:
        feedback = FeedbackModel(
            user_id=request.user_id,
            run_id=request.run_id,
            namespace=request.namespace,
            payload={"content": request.content, "metadata": request.metadata},
        )
        session.add(feedback)
        await self.services.memory_store.append(
            MemoryEvent(
                user_id=request.user_id,
                namespace=request.namespace,
                content=request.content,
                source_run_id=request.run_id,
                metadata=request.metadata,
            )
        )
        await session.commit()

    async def bootstrap_session(self, session: AsyncSession, user_id: str, profile_id: str, metadata: dict) -> None:
        result = await session.execute(
            select(IntegrationSessionModel).where(
                IntegrationSessionModel.user_id == user_id,
                IntegrationSessionModel.provider == "walmart",
            )
        )
        integration = result.scalar_one_or_none()
        if integration is None:
            integration = IntegrationSessionModel(user_id=user_id, provider="walmart", profile_id=profile_id)
            session.add(integration)
        integration.profile_id = profile_id
        integration.metadata_json = metadata
        await session.commit()
