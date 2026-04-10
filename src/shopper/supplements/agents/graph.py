from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Sequence
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from shopper.agents.llm import build_chat_model
from shopper.config import Settings
from shopper.supplements.agents.nodes.common import DEFAULT_VERIFIED_STORE_DOMAINS
from shopper.supplements.agents.state import (
    AnalysisSubgraphState,
    CheckoutSubgraphState,
    CriticSubgraphState,
    DiscoverySubgraphState,
    SupplementRunState,
)
from shopper.supplements.agents.subgraphs import (
    build_analysis_subgraph,
    build_checkout_subgraph,
    build_critic_subgraph,
    build_discovery_subgraph,
)
from shopper.supplements.agents.supervisor import route_from_critic, route_from_supervisor, supplement_supervisor_node
from shopper.supplements.events import SupplementEventEmitter, bind_event_emitter, emit_supplement_event
from shopper.supplements.schemas import StoreCart, SupplementCriticVerdict
from shopper.supplements.tools.shopify_mcp import search_store as default_search_store
from shopper.supplements.tools.shopify_mcp import update_cart as default_update_cart


TraceSource = Literal["api", "eval", "setup"]
DEFAULT_MAX_REPLANS = 0


def _phase_statuses(
    memory: str,
    discovery: str = "locked",
    analysis: str = "locked",
    checkout: str = "locked",
) -> dict[str, str]:
    return {
        "memory": memory,
        "discovery": discovery,
        "analysis": analysis,
        "checkout": checkout,
    }


def _graph_invoke_config(state: Dict[str, Any], source: TraceSource) -> Dict[str, Any]:
    metadata = {
        "phase": "supplements_phase3",
        "source": source,
        "supplement_run_id": state["run_id"],
        "user_id": state["user_id"],
    }
    return {
        "run_name": "{source}:supplement_graph".format(source=source),
        "tags": ["shopper", "supplements", source],
        "metadata": metadata,
    }


def _trace_outputs_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    critic_verdict = result.get("critic_verdict") or {}
    recommended_stack = result.get("recommended_stack") or {}
    return {
        "status": result.get("status"),
        "current_phase": result.get("current_phase"),
        "current_node": result.get("current_node"),
        "identified_need_count": len(result.get("identified_needs", [])),
        "comparison_count": len(result.get("product_comparisons", [])),
        "stack_item_count": len(recommended_stack.get("items", [])),
        "critic_decision": critic_verdict.get("decision"),
        "cart_count": len(result.get("store_carts", [])),
    }


def build_supplement_graph(
    *,
    chat_model: Optional[Any] = None,
    settings: Settings | None = None,
    search_store_fn=default_search_store,
    update_cart_fn=default_update_cart,
    store_domains: Sequence[str] = DEFAULT_VERIFIED_STORE_DOMAINS,
    max_products_per_result: int = 4,
    max_products_per_category: int = 6,
    max_replans: int = DEFAULT_MAX_REPLANS,
):
    resolved_settings = settings or Settings()
    resolved_chat_model = chat_model if chat_model is not None else build_chat_model(resolved_settings)

    discovery_subgraph = build_discovery_subgraph(
        chat_model=resolved_chat_model,
        search_store_fn=search_store_fn,
        store_domains=store_domains,
        max_products_per_result=max_products_per_result,
    )
    analysis_subgraph = build_analysis_subgraph(
        chat_model=resolved_chat_model,
        max_products_per_category=max_products_per_category,
    )
    critic_subgraph = build_critic_subgraph()
    checkout_subgraph = build_checkout_subgraph(update_cart_fn=update_cart_fn)

    async def load_memory_wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="memory",
            node_name="load_memory",
            message="Preparing the supplement run context.",
        )
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="node_entered",
            phase="memory",
            node_name="load_memory",
            message="Skipping episodic memory loading for the supplement demo flow.",
        )
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="node_completed",
            phase="memory",
            node_name="load_memory",
            message="Supplement intake context is ready.",
        )
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="memory",
            node_name="load_memory",
            message="Memory step complete.",
        )
        return {
            "identified_needs": [],
            "discovery_results": [],
            "product_comparisons": [],
            "recommended_stack": None,
            "critic_verdict": None,
            "store_carts": [],
            "approved_store_domains": [],
            "status": "running",
            "current_node": "load_memory",
            "current_phase": "discovery",
            "phase_statuses": _phase_statuses("completed", "pending"),
            "replan_count": 0,
            "latest_error": None,
        }

    async def discovery_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="discovery",
            node_name="discovery_subgraph",
            message="Identifying supplement needs and searching verified stores.",
        )
        result = await discovery_subgraph.ainvoke(
            DiscoverySubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                health_profile=state["health_profile"],
                identified_needs=state.get("identified_needs", []),
                discovery_results=state.get("discovery_results", []),
                context_metadata=[],
                messages=[HumanMessage(content="Identify supplement shopping needs and search verified stores.")],
            )
        )
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="discovery",
            node_name="discovery_subgraph",
            message="Store discovery is complete.",
            data={
                "need_count": len(result.get("identified_needs", [])),
                "category_count": len(result.get("discovery_results", [])),
            },
        )
        return {
            "identified_needs": result.get("identified_needs", []),
            "discovery_results": result.get("discovery_results", []),
            "product_comparisons": [],
            "recommended_stack": None,
            "critic_verdict": None,
            "store_carts": [],
            "approved_store_domains": [],
            "context_metadata": result.get("context_metadata", []),
            "status": "running",
            "current_node": "discovery_subgraph",
            "current_phase": "analysis",
            "phase_statuses": _phase_statuses("completed", "completed", "pending"),
            "latest_error": None,
        }

    async def analysis_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        is_replan = bool(state.get("critic_verdict")) and state["critic_verdict"].get("decision") == "failed"
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="analysis",
            node_name="analysis_subgraph",
            message=(
                "Rebuilding the supplement comparison and stack from critic feedback."
                if is_replan
                else "Comparing products and building the recommended stack."
            ),
            data={"replan_count": state.get("replan_count", 0)},
        )
        result = await analysis_subgraph.ainvoke(
            AnalysisSubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                health_profile=state["health_profile"],
                identified_needs=state.get("identified_needs", []),
                discovery_results=state.get("discovery_results", []),
                product_comparisons=state.get("product_comparisons", []),
                recommended_stack=state.get("recommended_stack"),
                replan_count=state.get("replan_count", 0),
                context_metadata=[],
                messages=[
                    HumanMessage(
                        content=(
                            "Rebuild the supplement stack using the latest critic feedback."
                            if is_replan
                            else "Compare products and build a practical supplement stack."
                        )
                    )
                ],
            )
        )
        return {
            "product_comparisons": result.get("product_comparisons", []),
            "recommended_stack": result.get("recommended_stack"),
            "critic_verdict": None,
            "store_carts": [],
            "approved_store_domains": [],
            "context_metadata": result.get("context_metadata", []),
            "status": "running",
            "current_node": "analysis_subgraph",
            "current_phase": "analysis",
            "phase_statuses": _phase_statuses("completed", "completed", "running"),
            "latest_error": None,
        }

    async def critic_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        result = await critic_subgraph.ainvoke(
            CriticSubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                health_profile=state["health_profile"],
                product_comparisons=state.get("product_comparisons", []),
                recommended_stack=state.get("recommended_stack"),
                critic_verdict=state.get("critic_verdict"),
                context_metadata=[],
                messages=[HumanMessage(content="Check the stack for safety, goal fit, and budget value.")],
            )
        )
        verdict = SupplementCriticVerdict.model_validate(result["critic_verdict"])
        should_retry = verdict.decision == "failed" and state.get("replan_count", 0) < max_replans

        if verdict.decision == "passed":
            next_status = "running"
            next_phase = "checkout"
            next_phase_statuses = _phase_statuses("completed", "completed", "completed", "pending")
            phase_message = "Analysis passed review and can move to checkout."
            next_replan_count = state.get("replan_count", 0)
        elif should_retry:
            next_status = "running"
            next_phase = "analysis"
            next_phase_statuses = _phase_statuses("completed", "completed", "running")
            phase_message = "Analysis needs another pass before checkout."
            next_replan_count = state.get("replan_count", 0) + 1
        elif verdict.decision == "manual_review_needed":
            next_status = "completed"
            next_phase = "analysis"
            next_phase_statuses = _phase_statuses("completed", "completed", "completed")
            phase_message = "Analysis completed with manual review required before checkout."
            next_replan_count = state.get("replan_count", 0)
        else:
            next_status = "failed"
            next_phase = "analysis"
            next_phase_statuses = _phase_statuses("completed", "completed", "failed")
            phase_message = "Analysis failed review and will stop before checkout."
            next_replan_count = state.get("replan_count", 0)

        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="analysis",
            node_name="critic",
            message=phase_message,
            data={
                "decision": verdict.decision,
                "issue_count": len(verdict.issues),
                "warning_count": len(verdict.warnings),
            },
        )

        if verdict.decision == "manual_review_needed":
            await emit_supplement_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="analysis",
                node_name="critic",
                message="Run completed with manual review needed.",
                data={"status": "completed", "decision": verdict.decision},
            )
        elif verdict.decision == "failed" and not should_retry:
            await emit_supplement_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="analysis",
                node_name="critic",
                message="Run failed before checkout.",
                data={"status": "failed", "decision": verdict.decision},
            )

        return {
            "critic_verdict": verdict.model_dump(mode="json"),
            "store_carts": [],
            "approved_store_domains": [],
            "context_metadata": result.get("context_metadata", []),
            "status": next_status,
            "current_node": "critic",
            "current_phase": next_phase,
            "phase_statuses": next_phase_statuses,
            "replan_count": next_replan_count,
        }

    async def checkout_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="checkout",
            node_name="checkout_subgraph",
            message="Building Shopify carts and checkout links for approval.",
        )
        result = await checkout_subgraph.ainvoke(
            CheckoutSubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                recommended_stack=state.get("recommended_stack"),
                store_carts=state.get("store_carts", []),
                approved_store_domains=state.get("approved_store_domains", []),
                status=state.get("status", "running"),
                current_node=state.get("current_node", "checkout_subgraph"),
                current_phase=state.get("current_phase", "checkout"),
                phase_statuses=state.get(
                    "phase_statuses",
                    _phase_statuses("completed", "completed", "completed", "running"),
                ),
                latest_error=state.get("latest_error"),
                context_metadata=[],
            )
        )
        carts = [StoreCart.model_validate(item) for item in result.get("store_carts", [])]
        ready_carts = [cart for cart in carts if cart.checkout_url]

        if not ready_carts:
            message = "Unable to build any checkout-ready carts."
            await emit_supplement_event(
                run_id=state["run_id"],
                event_type="error",
                phase="checkout",
                node_name="mcp_cart_builder",
                message=message,
                data={"store_count": len(carts)},
            )
            await emit_supplement_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="checkout",
                node_name="mcp_cart_builder",
                message="Run failed during checkout preparation.",
                data={"status": "failed"},
            )
            return {
                "store_carts": [cart.model_dump(mode="json") for cart in carts],
                "status": "failed",
                "current_node": "checkout_subgraph",
                "current_phase": "checkout",
                "phase_statuses": _phase_statuses("completed", "completed", "completed", "failed"),
                "latest_error": message,
            }

        await emit_supplement_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="checkout",
            node_name="checkout_subgraph",
            message="Checkout links are ready for approval.",
            data={"store_count": len(ready_carts)},
        )
        return {
            "store_carts": [cart.model_dump(mode="json") for cart in carts],
            "approved_store_domains": [],
            "status": "awaiting_approval",
            "current_node": "checkout_subgraph",
            "current_phase": "checkout",
            "phase_statuses": _phase_statuses("completed", "completed", "completed", "completed"),
            "latest_error": None,
        }

    graph = StateGraph(SupplementRunState)
    graph.add_node("supervisor", supplement_supervisor_node)
    graph.add_node("load_memory", load_memory_wrapper)
    graph.add_node("discovery_subgraph", discovery_subgraph_node)
    graph.add_node("analysis_subgraph", analysis_subgraph_node)
    graph.add_node("critic_subgraph", critic_subgraph_node)
    graph.add_node("checkout_subgraph", checkout_subgraph_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "load_memory": "load_memory",
            "discovery_subgraph": "discovery_subgraph",
            "analysis_subgraph": "analysis_subgraph",
            "critic_subgraph": "critic_subgraph",
            "checkout_subgraph": "checkout_subgraph",
            "end": END,
        },
    )
    graph.add_edge("load_memory", "discovery_subgraph")
    graph.add_edge("discovery_subgraph", "analysis_subgraph")
    graph.add_edge("analysis_subgraph", "critic_subgraph")
    graph.add_conditional_edges(
        "critic_subgraph",
        lambda state: route_from_critic(state, max_replans=max_replans),
        {
            "analysis_subgraph": "analysis_subgraph",
            "checkout_subgraph": "checkout_subgraph",
            "end": END,
        },
    )
    graph.add_edge("checkout_subgraph", END)
    return graph.compile()


async def invoke_supplement_graph(
    graph,
    state: Dict[str, Any],
    settings: Settings,
    source: TraceSource,
    event_emitter: Optional[SupplementEventEmitter] = None,
) -> Dict[str, Any]:
    trace_metadata = {
        "kind": "local",
        "project": settings.langsmith_project,
        "trace_id": str(uuid4()),
        "source": source,
    }
    working_state = dict(state)
    working_state["trace_metadata"] = trace_metadata
    invoke_config = _graph_invoke_config(working_state, source)

    async def invoke_graph() -> Dict[str, Any]:
        if event_emitter is not None:
            with bind_event_emitter(event_emitter):
                return await graph.ainvoke(working_state, config=invoke_config)
        return await graph.ainvoke(working_state, config=invoke_config)

    if settings.langsmith_tracing:
        if not settings.langsmith_api_key:
            raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING is enabled.")

        from langsmith import Client, trace, tracing_context

        client = Client(api_key=settings.langsmith_api_key)
        metadata = dict(invoke_config["metadata"])
        trace_inputs = {
            "run_id": working_state["run_id"],
            "user_id": working_state["user_id"],
            "source": source,
        }

        with tracing_context(
            enabled=True,
            client=client,
            project_name=settings.langsmith_project,
            tags=list(invoke_config["tags"]),
            metadata=metadata,
        ):
            async with trace(
                name="{source}:supplement_run".format(source=source),
                run_type="chain",
                inputs=trace_inputs,
            ) as root_run:
                trace_metadata["kind"] = "remote"
                trace_metadata["trace_id"] = str(root_run.trace_id)
                working_state["trace_metadata"] = trace_metadata
                result = await invoke_graph()
                root_run.end(outputs=_trace_outputs_summary(result))
    else:
        result = await invoke_graph()

    result["trace_metadata"] = trace_metadata
    return result
