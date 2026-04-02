from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from shopper.agents.events import EventEmitter, bind_event_emitter, emit_run_event
from shopper.agents.nodes import LoadMemoryNode
from shopper.agents.replan import derive_replan_feedback
from shopper.agents.state import PlannerState, PlanningSubgraphState
from shopper.agents.subgraphs import build_critic_subgraph, build_planning_subgraph
from shopper.agents.supervisor import route_from_critic, route_from_supervisor, supervisor_node
from shopper.agents.tools import RecipeSearchTool
from shopper.config import Settings
from shopper.memory import ContextAssembler, MemoryStore
from shopper.retrieval import QdrantRecipeStore, RecipeReranker


TraceSource = Literal["api", "eval", "setup"]
MAX_REPLAN_LOOPS = 1


def _phase_statuses(memory: str, planning: str) -> dict[str, str]:
    return {
        "memory": memory,
        "planning": planning,
        "shopping": "locked",
        "checkout": "locked",
    }


def _graph_invoke_config(state: Dict[str, Any], source: TraceSource) -> Dict[str, Any]:
    metadata = {
        "phase": "phase2",
        "source": source,
        "shopper_run_id": state["run_id"],
        "user_id": state["user_id"],
    }
    return {
        "run_name": "{source}:planner_graph".format(source=source),
        "tags": ["shopper", source],
        "metadata": metadata,
    }


def _trace_outputs_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    critic_verdict = result.get("critic_verdict") or {}
    return {
        "status": result.get("status"),
        "current_phase": result.get("current_phase"),
        "current_node": result.get("current_node"),
        "selected_meal_count": len(result.get("selected_meals", [])),
        "critic_passed": critic_verdict.get("passed"),
    }


def build_planner_graph(
    context_assembler: ContextAssembler,
    memory_store: MemoryStore,
    recipe_store: QdrantRecipeStore,
    reranker=None,
    chat_model=None,
):
    recipe_search = RecipeSearchTool(recipe_store=recipe_store, reranker=reranker or RecipeReranker())
    load_memory_node = LoadMemoryNode(context_assembler=context_assembler, memory_store=memory_store)
    planning_subgraph = build_planning_subgraph(
        context_assembler=context_assembler,
        recipe_search=recipe_search,
        chat_model=chat_model,
    )
    critic_subgraph = build_critic_subgraph(
        context_assembler=context_assembler,
        recipe_store=recipe_store,
        chat_model=chat_model,
    )

    async def load_memory_wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        await emit_run_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="memory",
            node_name="load_memory",
            message="Starting memory assembly for this run.",
        )
        result = await load_memory_node(state)
        await emit_run_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="memory",
            node_name="load_memory",
            message="Memory assembly complete.",
        )
        return {
            **result,
            "status": "running",
            "current_node": "load_memory",
            "current_phase": "planning",
            "phase_statuses": _phase_statuses("completed", "pending"),
        }

    async def planning_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        is_replan = bool(state.get("critic_verdict")) and not bool(state["critic_verdict"]["passed"])
        replan_feedback = derive_replan_feedback(state) if is_replan else {}
        planning_state = {**state, **replan_feedback}
        await emit_run_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="planning",
            node_name="planning_subgraph",
            message=(
                "Replanning meals from critic feedback."
                if is_replan
                else "Planning meals from the nutrition target and retrieval results."
            ),
            data={"replan_count": planning_state.get("replan_count", 0)},
        )
        result = await planning_subgraph.ainvoke(
            PlanningSubgraphState(
                run_id=planning_state["run_id"],
                user_id=planning_state["user_id"],
                user_profile=planning_state["user_profile"],
                user_preferences_learned=planning_state["user_preferences_learned"],
                retrieved_memories=planning_state["retrieved_memories"],
                critic_verdict=planning_state.get("critic_verdict"),
                repair_instructions=planning_state["repair_instructions"],
                blocked_recipe_ids=planning_state["blocked_recipe_ids"],
                avoid_cuisines=planning_state["avoid_cuisines"],
                replan_count=planning_state.get("replan_count", 0),
                context_metadata=[],
                selected_meals=planning_state.get("selected_meals", []),
                messages=[
                    HumanMessage(
                        content=(
                            "Revise the 7 day nutrition-aligned meal plan using the latest critic feedback."
                            if is_replan
                            else "Create a 7 day nutrition-aligned meal plan."
                        )
                    )
                ],
            )
        )
        return {
            **replan_feedback,
            "nutrition_plan": result["nutrition_plan"],
            "selected_meals": result["selected_meals"],
            "context_metadata": result["context_metadata"],
            "current_node": "planning_subgraph",
            "status": "running",
            "current_phase": "planning",
            "phase_statuses": _phase_statuses("completed", "running"),
            "trace_metadata": state["trace_metadata"],
        }

    async def critic_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        result = await critic_subgraph.ainvoke(state)
        verdict = result["critic_verdict"]
        passed = bool(verdict["passed"])
        should_retry = (not passed) and state["replan_count"] < MAX_REPLAN_LOOPS
        await emit_run_event(
            run_id=state["run_id"],
            event_type="phase_completed",
            phase="planning",
            node_name="critic",
            message="Planning phase {status} verification.".format(
                status="passed" if passed else "failed"
            ),
            data={"passed": passed},
        )
        if passed or not should_retry:
            await emit_run_event(
                run_id=state["run_id"],
                event_type="run_completed",
                phase="planning",
                node_name="critic",
                message="Run {status}.".format(status="completed" if passed else "failed"),
                data={"status": "completed" if passed else "failed"},
            )
        return {
            "critic_verdict": verdict,
            "repair_instructions": result.get("repair_instructions", []),
            "context_metadata": result.get("context_metadata", []),
            "status": "completed" if passed else "running" if should_retry else "failed",
            "current_node": "critic",
            "current_phase": "planning",
            "phase_statuses": _phase_statuses(
                "completed",
                "completed" if passed else "running" if should_retry else "failed",
            ),
            "trace_metadata": state["trace_metadata"],
        }

    graph = StateGraph(PlannerState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("load_memory", load_memory_wrapper)
    graph.add_node("planning_subgraph", planning_subgraph_node)
    graph.add_node("critic_subgraph", critic_subgraph_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "load_memory": "load_memory",
            "planning_subgraph": "planning_subgraph",
        },
    )
    graph.add_edge("load_memory", "planning_subgraph")
    graph.add_edge("planning_subgraph", "critic_subgraph")
    graph.add_conditional_edges(
        "critic_subgraph",
        lambda state: route_from_critic(state, max_replans=MAX_REPLAN_LOOPS),
        {
            "planning_subgraph": "planning_subgraph",
            "end": END,
        },
    )
    return graph.compile()


async def invoke_planner_graph(
    graph,
    state: Dict[str, Any],
    settings: Settings,
    source: TraceSource,
    event_emitter: Optional[EventEmitter] = None,
) -> Dict[str, Any]:
    trace_metadata = {
        "kind": "local",
        "project": settings.langsmith_project,
        "trace_id": str(uuid4()),
        "source": source,
    }
    state["trace_metadata"] = trace_metadata
    invoke_config = _graph_invoke_config(state, source)

    async def invoke_graph() -> Dict[str, Any]:
        if event_emitter is not None:
            with bind_event_emitter(event_emitter):
                return await graph.ainvoke(state, config=invoke_config)
        return await graph.ainvoke(state, config=invoke_config)

    if settings.langsmith_tracing:
        if not settings.langsmith_api_key:
            raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING is enabled.")

        from langsmith import Client, trace, tracing_context

        client = Client(api_key=settings.langsmith_api_key)
        metadata = dict(invoke_config["metadata"])
        trace_inputs = {
            "run_id": state["run_id"],
            "user_id": state["user_id"],
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
                name="{source}:planner_run".format(source=source),
                run_type="chain",
                inputs=trace_inputs,
            ) as root_run:
                trace_metadata["kind"] = "remote"
                trace_metadata["trace_id"] = str(root_run.trace_id)
                result = await invoke_graph()
                root_run.end(outputs=_trace_outputs_summary(result))
    else:
        result = await invoke_graph()

    result["trace_metadata"] = trace_metadata
    return result
