from __future__ import annotations

from typing import Any, Dict
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from shopper.agents.state import PlannerState, PlanningSubgraphState
from shopper.agents.subgraphs import build_planning_subgraph
from shopper.agents.supervisor import supervisor_node
from shopper.config import Settings
from shopper.memory import ContextAssembler


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


async def invoke_planner_graph(graph, state: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    result = await graph.ainvoke(state)
    trace_id = uuid4()
    trace_metadata = {"kind": "local", "project": settings.langchain_project, "trace_id": str(trace_id)}
    if settings.enable_remote_langsmith:
        assert settings.langchain_api_key
        from langsmith import Client

        client = Client(api_key=settings.langchain_api_key)
        client.create_run(
            name="planner_run",
            run_type="chain",
            project_name=settings.langchain_project,
            id=UUID(str(trace_id)),
            inputs=state,
            outputs=result,
            extra={"metadata": {"phase": "phase1", "context_metadata": result["context_metadata"]}},
        )
        trace_metadata["kind"] = "remote"
    result["trace_metadata"] = trace_metadata
    return result
