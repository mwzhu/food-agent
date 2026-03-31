from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from shopper.agents.state import PlannerState, PlanningSubgraphState
from shopper.agents.subgraphs import build_planning_subgraph
from shopper.agents.supervisor import supervisor_node
from shopper.config import Settings
from shopper.memory import ContextAssembler


TraceSource = Literal["api", "eval", "setup"]


def build_planner_graph(context_assembler: ContextAssembler):
    planning_subgraph = build_planning_subgraph(context_assembler=context_assembler)

    async def planning_subgraph_node(state: Dict[str, Any]) -> Dict[str, Any]:
        result = await planning_subgraph.ainvoke(
            PlanningSubgraphState(
                run_id=state["run_id"],
                user_id=state["user_id"],
                user_profile=state["user_profile"],
                context_metadata=[],
                selected_meals=[],
                messages=[HumanMessage(content="Create a 7 day nutrition-aligned meal plan.")],
            )
        )
        return {
            "nutrition_plan": result["nutrition_plan"],
            "selected_meals": result["selected_meals"],
            "context_metadata": result["context_metadata"],
            "status": "completed",
            "current_node": "planning_subgraph",
            "trace_metadata": state["trace_metadata"],
        }

    graph = StateGraph(PlannerState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planning_subgraph", planning_subgraph_node)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "planning_subgraph")
    graph.add_edge("planning_subgraph", END)
    return graph.compile()


async def invoke_planner_graph(
    graph,
    state: Dict[str, Any],
    settings: Settings,
    source: TraceSource,
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
                    "phase": "phase1",
                    "source": source,
                }
            },
        )
    result = await graph.ainvoke(state)
    if settings.langsmith_tracing:
        client.update_run(
            run_id=UUID(str(trace_id)),
            end_time=datetime.now(timezone.utc),
            outputs=result,
            extra={
                "metadata": {
                    "phase": "phase1",
                    "source": source,
                    "context_metadata": result["context_metadata"],
                }
            },
        )
        trace_metadata["kind"] = "remote"
    result["trace_metadata"] = trace_metadata
    return result
