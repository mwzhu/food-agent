from __future__ import annotations

from shopper.agents.subgraphs.planning import route_planning_start
from shopper.agents.supervisor import route_from_critic, route_from_supervisor


def test_supervisor_routes_initial_runs_to_memory_loading():
    assert route_from_supervisor({"replan_count": 0}) == "load_memory"


def test_supervisor_routes_replans_back_to_planning():
    assert route_from_supervisor({"replan_count": 1}) == "planning_subgraph"


def test_supervisor_routes_planning_runs_straight_to_planning():
    assert route_from_supervisor({"current_phase": "planning"}) == "planning_subgraph"


def test_critic_routes_failed_verdicts_back_to_planning_until_limit():
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 0}, max_replans=1) == "planning_subgraph"
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 1}, max_replans=1) == "end"
    assert route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 1}, max_replans=1) == "end"


def test_critic_routes_successful_planning_to_end():
    assert route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 0}) == "end"


def test_planning_subgraph_starts_with_nutrition_then_skips_to_meal_selector_on_repair():
    assert route_planning_start({}) == "nutrition_planner"
    assert route_planning_start({"replan_count": 1}) == "meal_selector"


def test_planning_subgraph_repair_skips_to_grocery_builder_for_fulfillment_only_failures():
    assert route_planning_start(
        {
            "replan_count": 1,
            "issue_finding_codes": ["P_BUDGET", "P_STORE_CHOICE"],
        }
    ) == "grocery_builder"


def test_planning_subgraph_repair_uses_meal_selector_when_any_meal_level_issue_is_present():
    assert route_planning_start(
        {
            "replan_count": 1,
            "issue_finding_codes": ["P_BUDGET", "P_GROUNDEDNESS"],
        }
    ) == "meal_selector"
