from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from shopper.supplements.agents.nodes.common import extract_allergens, normalize_text
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import (
    HealthProfile,
    ProductComparison,
    SupplementCriticFinding,
    SupplementCriticVerdict,
    SupplementStack,
)


async def supplement_critic(state: dict[str, Any]) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="analysis",
        node_name="supplement_critic",
        message="Checking the recommended stack for safety, goal fit, and budget value.",
    )

    health_profile = HealthProfile.model_validate(state["health_profile"])
    product_comparisons = [ProductComparison.model_validate(item) for item in state.get("product_comparisons", [])]
    recommended_stack = SupplementStack.model_validate(state.get("recommended_stack") or {})
    verdict = _evaluate_stack(
        health_profile=health_profile,
        product_comparisons=product_comparisons,
        recommended_stack=recommended_stack,
    )

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="analysis",
        node_name="supplement_critic",
        message="Supplement critic decision: {decision}.".format(decision=verdict.decision),
        data={
            "decision": verdict.decision,
            "issue_count": len(verdict.issues),
            "warning_count": len(verdict.warnings),
        },
    )

    return {
        "critic_verdict": verdict.model_dump(mode="json"),
        "messages": [
            AIMessage(
                content="Supplement critic returned {decision}.".format(decision=verdict.decision)
            )
        ],
    }


def _evaluate_stack(
    *,
    health_profile: HealthProfile,
    product_comparisons: list[ProductComparison],
    recommended_stack: SupplementStack,
) -> SupplementCriticVerdict:
    issues: list[str] = []
    warnings: list[str] = list(recommended_stack.warnings)
    findings: list[SupplementCriticFinding] = []
    comparison_lookup = {
        (comparison.category, compared_product.product.store_domain, compared_product.product.product_id): compared_product
        for comparison in product_comparisons
        for compared_product in comparison.ranked_products
    }

    if not recommended_stack.items:
        message = "No supplement stack items were selected."
        issues.append(message)
        findings.append(
            SupplementCriticFinding(concern="goal_alignment", severity="issue", message=message)
        )

    allergy_set = {allergy.lower() for allergy in health_profile.allergies}
    for item in recommended_stack.items:
        compared_product = comparison_lookup.get((item.category, item.product.store_domain, item.product.product_id))
        item_text = normalize_text(item.product.title, item.product.description, " ".join(item.cautions))
        detected_allergens = set(extract_allergens(item_text))
        if compared_product is not None:
            detected_allergens.update(allergen.lower() for allergen in compared_product.ingredient_analysis.allergens)
        conflicting_allergens = allergy_set & {allergen.lower() for allergen in detected_allergens}
        if conflicting_allergens:
            message = (
                "{title} may conflict with reported allergies: {allergens}."
            ).format(
                title=item.product.title,
                allergens=", ".join(sorted(conflicting_allergens)),
            )
            issues.append(message)
            findings.append(
                SupplementCriticFinding(concern="safety", severity="issue", message=message)
            )

    uncovered_goals = [
        goal
        for goal in health_profile.health_goals
        if not any(_goal_supported(goal, item) for item in recommended_stack.items)
    ]
    for goal in uncovered_goals:
        message = "The recommended stack does not clearly address the goal '{goal}'.".format(goal=goal)
        issues.append(message)
        findings.append(
            SupplementCriticFinding(concern="goal_alignment", severity="issue", message=message)
        )

    if recommended_stack.total_monthly_cost is not None:
        if recommended_stack.total_monthly_cost > health_profile.monthly_budget:
            message = (
                "Estimated monthly cost ${total:.2f} exceeds the ${budget:.2f} budget."
            ).format(
                total=recommended_stack.total_monthly_cost,
                budget=health_profile.monthly_budget,
            )
            issues.append(message)
            findings.append(
                SupplementCriticFinding(concern="value", severity="issue", message=message)
            )
        elif health_profile.monthly_budget and recommended_stack.total_monthly_cost >= health_profile.monthly_budget * 0.9:
            message = "Estimated monthly cost consumes most of the stated budget."
            warnings.append(message)
            findings.append(
                SupplementCriticFinding(concern="value", severity="warning", message=message)
            )

    manual_review_reason = None
    if not issues and (health_profile.medications or health_profile.conditions):
        manual_review_reason = (
            "Manual review recommended because the user reported medications or conditions that need a human safety check."
        )
        warnings.append(manual_review_reason)
        findings.append(
            SupplementCriticFinding(concern="safety", severity="issue", message=manual_review_reason)
        )

    issues = _dedupe_strings(issues)
    warnings = _dedupe_strings(warnings)
    findings = _dedupe_findings(findings)

    if issues:
        decision = "failed"
        summary = "The supplement stack has blocking issues that should be fixed before checkout."
    elif manual_review_reason is not None:
        decision = "manual_review_needed"
        summary = "The stack is directionally reasonable, but a clinician or pharmacist should review it first."
    else:
        decision = "passed"
        summary = "The stack passed the current safety, goal, and budget checks."

    return SupplementCriticVerdict(
        decision=decision,
        summary=summary,
        issues=issues,
        warnings=warnings,
        findings=findings,
        manual_review_reason=manual_review_reason,
    )


def _goal_supported(goal: str, item) -> bool:
    normalized_goal = goal.strip().lower()
    if item.goal.strip().lower() == normalized_goal:
        return True
    goal_tokens = [token for token in normalized_goal.split() if len(token) > 3]
    combined = normalize_text(
        item.category,
        item.goal,
        item.product.title,
        item.product.description,
        item.rationale,
    )
    return any(token in combined for token in goal_tokens)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _dedupe_findings(findings: list[SupplementCriticFinding]) -> list[SupplementCriticFinding]:
    deduped: list[SupplementCriticFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.concern, finding.severity, finding.message)
        if key in seen:
            continue
        deduped.append(finding)
        seen.add(key)
    return deduped
