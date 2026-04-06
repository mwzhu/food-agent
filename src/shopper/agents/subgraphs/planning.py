from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from shopper.agents.nodes import GroceryBuilderNode, MealSelectorNode, NutritionPlannerNode, PriceOptimizerNode
from shopper.agents.replan import FULFILLMENT_ONLY_ISSUE_CODES
from shopper.agents.state import PlanningSubgraphState
from shopper.agents.tools import RecipeSearchTool
from shopper.memory import ContextAssembler


MEAL_LEVEL_ISSUE_CODES = frozenset({
    "P_NUTRITION_PLAN",
    "P_MACRO_MISS",
    "P_MACRO_DRIFT",
    "P_SAFETY",
    "P_GROUNDEDNESS",
    "P_SCHEDULE",
    "P_VARIETY",
    "P_LLM_REVIEW",
})


def route_planning_start(state: PlanningSubgraphState) -> str:
    if state.get("replan_count", 0) == 0:
        return "nutrition_planner"

    issue_finding_codes = {
        code
        for code in state.get("issue_finding_codes", [])
        if code
    }
    if not issue_finding_codes:
        return "meal_selector"
    if issue_finding_codes & MEAL_LEVEL_ISSUE_CODES:
        return "meal_selector"
    if issue_finding_codes <= FULFILLMENT_ONLY_ISSUE_CODES:
        return "grocery_builder"
    return "meal_selector"


def build_planning_subgraph(
    get_fridge_contents_tool,
    context_assembler: ContextAssembler,
    recipe_search: RecipeSearchTool,
    chat_model=None,
):
    graph = StateGraph(PlanningSubgraphState)
    graph.add_node("nutrition_planner", NutritionPlannerNode(context_assembler=context_assembler))
    graph.add_node(
        "meal_selector",
        MealSelectorNode(
            context_assembler=context_assembler,
            recipe_search=recipe_search,
            chat_model=chat_model,
        ),
    )
    graph.add_node(
        "grocery_builder",
        GroceryBuilderNode(
            get_fridge_contents_tool=get_fridge_contents_tool,
        ),
    )
    graph.add_node(
        "price_optimizer",
        PriceOptimizerNode(
            context_assembler=context_assembler,
            chat_model=chat_model,
        ),
    )
    graph.add_conditional_edges(
        START,
        route_planning_start,
        {
            "nutrition_planner": "nutrition_planner",
            "meal_selector": "meal_selector",
            "grocery_builder": "grocery_builder",
        },
    )
    graph.add_edge("nutrition_planner", "meal_selector")
    graph.add_edge("meal_selector", "grocery_builder")
    graph.add_edge("grocery_builder", "price_optimizer")
    graph.add_edge("price_optimizer", END)
    return graph.compile()
