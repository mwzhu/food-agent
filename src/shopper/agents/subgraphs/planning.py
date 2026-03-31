from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.agents.nodes import MealSelectorNode, NutritionPlannerNode
from shopper.agents.state import PlanningSubgraphState
from shopper.memory import ContextAssembler


def build_planning_subgraph(context_assembler: ContextAssembler):
    graph = StateGraph(PlanningSubgraphState)
    graph.add_node("nutrition_planner", NutritionPlannerNode(context_assembler=context_assembler))
    graph.add_node("meal_selector", MealSelectorNode(context_assembler=context_assembler))
    graph.add_edge(START, "nutrition_planner")
    graph.add_edge("nutrition_planner", "meal_selector")
    graph.add_edge("meal_selector", END)
    return graph.compile()
