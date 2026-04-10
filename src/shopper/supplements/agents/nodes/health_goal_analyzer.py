from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.llm import invoke_structured
from shopper.supplements.agents.nodes.common import category_already_covered
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import HealthProfile, SupplementNeed


SYSTEM_PROMPT = """
You are planning supplement shopping search categories for a comparison agent.
Return 1-4 practical supplement needs based only on the provided profile.
Avoid diagnosis, treatment claims, and niche protocols.
Prefer mainstream retail categories that are likely to exist in Shopify stores.
Do not repeat supplements the user already takes unless there is a clear form or value reason.
Priorities use 1 as the highest priority.
""".strip()


@dataclass(frozen=True)
class NeedTemplate:
    category: str
    rationale: str
    search_queries: tuple[str, ...]


@dataclass(frozen=True)
class GoalRule:
    keywords: tuple[str, ...]
    templates: tuple[NeedTemplate, ...]


class HealthGoalAnalysisResponse(BaseModel):
    needs: list[SupplementNeed] = Field(default_factory=list)


GOAL_RULES = (
    GoalRule(
        keywords=("sleep", "rest", "insomnia", "bedtime"),
        templates=(
            NeedTemplate(
                category="magnesium",
                rationale="Magnesium is a common first-pass category for sleep support and evening recovery.",
                search_queries=("sleep magnesium", "magnesium glycinate sleep", "magnesium l-threonate"),
            ),
        ),
    ),
    GoalRule(
        keywords=("recovery", "strength", "performance", "muscle", "workout"),
        templates=(
            NeedTemplate(
                category="creatine",
                rationale="Creatine is one of the most established categories for performance and recovery support.",
                search_queries=("creatine hmb", "creatine monohydrate", "creatine"),
            ),
            NeedTemplate(
                category="protein powder",
                rationale="Protein powder can help fill protein gaps when recovery or lean mass is a goal.",
                search_queries=("whey protein isolate", "grass fed whey protein", "protein powder"),
            ),
        ),
    ),
    GoalRule(
        keywords=("focus", "brain", "cognition", "clarity"),
        templates=(
            NeedTemplate(
                category="omega-3",
                rationale="Omega-3 products are common for brain-health and foundational support comparisons.",
                search_queries=("omega-3 dha", "fish oil omega 3", "dha epa"),
            ),
        ),
    ),
    GoalRule(
        keywords=("energy", "wellness", "foundation", "immune", "immunity"),
        templates=(
            NeedTemplate(
                category="multivitamin",
                rationale="A multivitamin is a straightforward foundational category when general wellness is the goal.",
                search_queries=("multivitamin", "daily essential multivitamin", "daily multivitamin"),
            ),
            NeedTemplate(
                category="vitamin d",
                rationale="Vitamin D is a common foundational category when users want broad wellness support.",
                search_queries=("vitamin d3 k2", "vitamin d3", "vitamin d"),
            ),
        ),
    ),
    GoalRule(
        keywords=("gut", "digestion", "digestive", "bloat"),
        templates=(
            NeedTemplate(
                category="probiotic",
                rationale="Probiotic products are a common retail category for digestive support comparisons.",
                search_queries=("probiotic", "digestive probiotic", "gut health probiotic"),
            ),
        ),
    ),
    GoalRule(
        keywords=("hydration", "electrolyte", "endurance", "cramps"),
        templates=(
            NeedTemplate(
                category="electrolytes",
                rationale="Electrolytes are an easy category to compare when hydration or training support is a goal.",
                search_queries=("electrolytes", "hydration electrolytes", "performance hydration"),
            ),
        ),
    ),
)


async def health_goal_analyzer(
    state: dict[str, Any],
    *,
    chat_model: Optional[Any] = None,
) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="discovery",
        node_name="health_goal_analyzer",
        message="Translating the health profile into supplement shopping categories.",
    )

    profile = HealthProfile.model_validate(state["health_profile"])
    needs = await _llm_needs(profile, chat_model=chat_model)
    if not needs:
        needs = _fallback_needs(profile)
    needs = _normalize_needs(needs, profile)

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="discovery",
        node_name="health_goal_analyzer",
        message="Identified {count} supplement shopping categories.".format(count=len(needs)),
        data={
            "categories": [need.category for need in needs],
            "need_count": len(needs),
        },
    )

    return {
        "identified_needs": [need.model_dump(mode="json") for need in needs],
        "messages": [
            AIMessage(
                content="Identified supplement categories: {categories}".format(
                    categories=", ".join(need.category for need in needs) or "none"
                )
            )
        ],
    }


async def _llm_needs(profile: HealthProfile, *, chat_model: Optional[Any]) -> list[SupplementNeed]:
    response = await invoke_structured(
        chat_model,
        HealthGoalAnalysisResponse,
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=True)),
        ],
    )
    if response is None:
        return []
    return list(response.needs)


def _fallback_needs(profile: HealthProfile) -> list[SupplementNeed]:
    needs: list[SupplementNeed] = []
    seen_categories: set[str] = set()
    next_priority = 1

    for goal in profile.health_goals:
        lowered_goal = goal.lower()
        for rule in GOAL_RULES:
            if not any(keyword in lowered_goal for keyword in rule.keywords):
                continue
            template = _select_template(rule, profile, seen_categories)
            if template is None:
                break
            needs.append(
                SupplementNeed(
                    category=template.category,
                    goal=goal,
                    rationale=template.rationale,
                    search_queries=list(template.search_queries),
                    priority=next_priority,
                )
            )
            seen_categories.add(template.category.lower())
            next_priority += 1
            break

    if not needs:
        needs.append(_default_fallback_need(profile))

    return needs[:4]


def _select_template(
    rule: GoalRule,
    profile: HealthProfile,
    seen_categories: set[str],
) -> Optional[NeedTemplate]:
    for template in rule.templates:
        normalized_category = template.category.lower()
        if normalized_category in seen_categories:
            continue
        if category_already_covered(template.category, profile.current_supplements):
            continue
        return template
    return None


def _normalize_needs(needs: list[SupplementNeed], profile: HealthProfile) -> list[SupplementNeed]:
    normalized: list[SupplementNeed] = []
    seen_categories: set[str] = set()
    next_priority = 1

    for need in sorted(needs, key=lambda item: (item.priority, item.category.lower())):
        normalized_category = need.category.strip().lower()
        if not normalized_category or normalized_category in seen_categories:
            continue
        if category_already_covered(need.category, profile.current_supplements):
            continue
        search_queries = [query for query in need.search_queries if query.strip()]
        if not search_queries:
            search_queries = [need.category]
        normalized.append(
            need.model_copy(
                update={
                    "search_queries": search_queries[:3],
                    "priority": next_priority,
                    "goal": need.goal or profile.health_goals[0],
                }
            )
        )
        seen_categories.add(normalized_category)
        next_priority += 1
        if len(normalized) >= 4:
            break

    if normalized:
        return normalized
    return [_default_fallback_need(profile)]


def _default_fallback_need(profile: HealthProfile) -> SupplementNeed:
    fallback_templates = (
        NeedTemplate(
            category="multivitamin",
            rationale="A multivitamin is a practical fallback category for a first-pass supplement comparison.",
            search_queries=("multivitamin", "daily essential multivitamin"),
        ),
        NeedTemplate(
            category="omega-3",
            rationale="Omega-3 is a broad, practical fallback category when the user's goals are vague.",
            search_queries=("omega-3 dha", "fish oil omega 3"),
        ),
        NeedTemplate(
            category="magnesium",
            rationale="Magnesium is a common fallback category for recovery and evening support.",
            search_queries=("magnesium", "sleep magnesium"),
        ),
    )
    for template in fallback_templates:
        if category_already_covered(template.category, profile.current_supplements):
            continue
        return SupplementNeed(
            category=template.category,
            goal=profile.health_goals[0],
            rationale=template.rationale,
            search_queries=list(template.search_queries),
            priority=1,
        )
    return SupplementNeed(
        category="supplement support",
        goal=profile.health_goals[0],
        rationale="A generic support category keeps search moving when every common fallback is already covered.",
        search_queries=["daily supplement support"],
        priority=1,
    )
