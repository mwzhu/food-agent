from __future__ import annotations

from shopper.agents.supervisor import route_from_critic, route_from_supervisor


def test_supervisor_routes_initial_runs_to_memory_loading():
    assert route_from_supervisor({"replan_count": 0}) == "load_memory"


def test_supervisor_routes_replans_back_to_planning():
    assert route_from_supervisor({"replan_count": 1}) == "planning_subgraph"


def test_supervisor_routes_shopping_runs_straight_to_shopping():
    assert route_from_supervisor({"current_phase": "shopping"}) == "shopping_subgraph"


def test_supervisor_routes_checkout_runs_to_checkout_subgraph():
    assert route_from_supervisor({"current_phase": "checkout"}) == "checkout_subgraph"


def test_critic_routes_failed_verdicts_back_to_planning_until_limit():
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 0}, max_replans=1) == "planning_subgraph"
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 1}, max_replans=1) == "end"
    assert route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 1}, max_replans=1) == "shopping_subgraph"


def test_critic_routes_successful_planning_to_shopping():
    assert (
        route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 0, "current_phase": "planning"})
        == "shopping_subgraph"
    )


def test_critic_ends_after_shopping_review():
    assert route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 0, "current_phase": "shopping"}) == "end"
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 0, "current_phase": "shopping"}) == "end"
