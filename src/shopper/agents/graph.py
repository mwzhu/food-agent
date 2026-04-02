from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from shopper.agents.events import EventEmitter, bind_event_emitter, emit_run_event
from shopper.agents.nodes import LoadMemoryNode, SubstitutionNode
from shopper.agents.state import PlannerState, PlanningSubgraphState
from shopper.agents.subgraphs import build_critic_subgraph, build_planning_subgraph
from shopper.agents.supervisor import route_from_critic, route_from_supervisor, supervisor_node
from shopper.agents.tools import RecipeSearchTool
from shopper.config import Settings
from shopper.memory import ContextAssembler, MemoryStore
from shopper.retrieval import QdrantRecipeStore, RecipeReranker


TraceSource = Literal["api", "eval", "setup"]
MAX_REPLAN_LOOPS = 3


def _phase_statuses(memory: str, planning: str) -> dict[str, str]:
    return {
        "memory": memory,
        "planning": planning,
        "shopping": "locked",
        "checkout": "locked",
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
    substitution_node = SubstitutionNode(chat_model=chat_model)
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
        await emit_run_event(
            run_id=state["run_id"],
            event_type="phase_started",
            phase="planning",
            node_name="planning_subgraph",
            message="Planning meals from the nutrition target and retrieval results.",
        )
        result = await planning_subgraph.ainvoke(
            PlanningSubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                user_profile=state["user_profile"],
                user_preferences_learned=state["user_preferences_learned"],
                retrieved_memories=state["retrieved_memories"],
                repair_instructions=state["repair_instructions"],
                blocked_recipe_ids=state["blocked_recipe_ids"],
                avoid_cuisines=state["avoid_cuisines"],
                context_metadata=[],
                selected_meals=[],
                messages=[HumanMessage(content="Create a 7 day nutrition-aligned meal plan.")],
            )
        )
        return {
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

    async def substitution_wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        return await substitution_node(state)

    graph = StateGraph(PlannerState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("load_memory", load_memory_wrapper)
    graph.add_node("planning_subgraph", planning_subgraph_node)
    graph.add_node("critic_subgraph", critic_subgraph_node)
    graph.add_node("substitution", substitution_wrapper)
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
            "substitution": "substitution",
            "end": END,
        },
    )
    graph.add_edge("substitution", "supervisor")
    return graph.compile()


async def invoke_planner_graph(
    graph,
    state: Dict[str, Any],
    settings: Settings,
    source: TraceSource,
    event_emitter: Optional[EventEmitter] = None,
) -> Dict[str, Any]:
    trace_id = uuid4()
    start_time = datetime.now(timezone.utc)
    trace_metadata = {
        "kind": "local",
        "project": settings.langsmith_project,
        "trace_id": str(trace_id),
        "source": source,
    }
    if settings.langsmith_tracing:
        assert settings.langsmith_api_key
        from langsmith import Client

        client = Client(api_key=settings.langsmith_api_key)
        client.create_run(
            name="{source}:planner_run".format(source=source),
            run_type="chain",
            project_name=settings.langsmith_project,
            id=UUID(str(trace_id)),
            inputs=state,
            start_time=start_time,
            extra={
                "metadata": {
                    "phase": "phase2",
                    "source": source,
                }
            },
        )
    if event_emitter is not None:
        with bind_event_emitter(event_emitter):
            result = await graph.ainvoke(state)
    else:
        result = await graph.ainvoke(state)
    if settings.langsmith_tracing:
        client.update_run(
            run_id=UUID(str(trace_id)),
            end_time=datetime.now(timezone.utc),
            outputs=result,
            extra={
                "metadata": {
                    "phase": "phase2",
                    "source": source,
                    "context_metadata": result["context_metadata"],
                }
            },
        )
        trace_metadata["kind"] = "remote"
    result["trace_metadata"] = trace_metadata
    return result
