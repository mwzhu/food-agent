from __future__ import annotations

from shopper.agents.supervisor import route_from_critic, route_from_supervisor


def test_supervisor_routes_initial_runs_to_memory_loading():
    assert route_from_supervisor({"replan_count": 0}) == "load_memory"


def test_supervisor_routes_replans_back_to_planning():
    assert route_from_supervisor({"replan_count": 1}) == "planning_subgraph"


def test_critic_routes_failed_verdicts_to_substitution_until_limit():
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 0}, max_replans=3) == "substitution"
    assert route_from_critic({"critic_verdict": {"passed": False}, "replan_count": 3}, max_replans=3) == "end"
    assert route_from_critic({"critic_verdict": {"passed": True}, "replan_count": 1}, max_replans=3) == "end"
