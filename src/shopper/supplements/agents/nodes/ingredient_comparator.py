from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from shopper.agents.llm import invoke_structured
from shopper.supplements.agents.nodes.common import (
    category_keywords,
    coerce_shopify_product,
    estimate_monthly_cost,
    estimate_price_per_serving,
    estimate_serving_details,
    extract_allergens,
    extract_bioavailability_notes,
    extract_dosage_mentions,
    matched_keywords,
    product_price,
    product_text,
)
from shopper.supplements.events import emit_supplement_event
from shopper.supplements.schemas import (
    CategoryDiscoveryResult,
    ComparedProduct,
    IngredientAnalysis,
    ProductComparison,
    ShopifyProduct,
)


SYSTEM_PROMPT = """
You compare consumer supplement products for one shopping category.
Use only the evidence provided.
Rank products by ingredient fit, dosage/form quality, bioavailability clues, price efficiency, and obvious safety notes.
Do not invent ingredients, certifications, or serving data that is not in the payload.
""".strip()


class ComparedProductDecision(BaseModel):
    store_domain: str
    product_id: str
    rank: int = Field(default=1, ge=1)
    score: Optional[float] = Field(default=None, ge=0)
    rationale: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ingredient_analysis: IngredientAnalysis = Field(default_factory=IngredientAnalysis)
    monthly_cost: Optional[float] = None


class CategoryComparisonDecision(BaseModel):
    summary: str = ""
    ranked_products: list[ComparedProductDecision] = Field(default_factory=list)


async def ingredient_comparator(
    state: dict[str, Any],
    *,
    chat_model: Optional[Any] = None,
    max_products_per_category: int = 6,
) -> dict[str, Any]:
    run_id = state["run_id"]
    await emit_supplement_event(
        run_id=run_id,
        event_type="node_entered",
        phase="analysis",
        node_name="ingredient_comparator",
        message="Comparing supplement ingredients, forms, and value across stores.",
    )

    discovery_results = [CategoryDiscoveryResult.model_validate(item) for item in state.get("discovery_results", [])]
    comparisons = await asyncio.gather(
        *(
            _compare_category(
                discovery_result=result,
                chat_model=chat_model,
                max_products_per_category=max_products_per_category,
            )
            for result in discovery_results
        )
    )

    await emit_supplement_event(
        run_id=run_id,
        event_type="node_completed",
        phase="analysis",
        node_name="ingredient_comparator",
        message="Completed {count} category comparisons.".format(count=len(comparisons)),
        data={
            "comparison_count": len(comparisons),
            "top_picks": [
                {
                    "category": comparison.category,
                    "product_id": comparison.top_pick_product_id,
                    "store_domain": comparison.top_pick_store_domain,
                }
                for comparison in comparisons
            ],
        },
    )

    return {
        "product_comparisons": [comparison.model_dump(mode="json") for comparison in comparisons],
        "messages": [
            AIMessage(
                content="Compared supplement options for {count} categories.".format(count=len(comparisons))
            )
        ],
    }


async def _compare_category(
    *,
    discovery_result: CategoryDiscoveryResult,
    chat_model: Optional[Any],
    max_products_per_category: int,
) -> ProductComparison:
    fallback = _fallback_compare_category(
        discovery_result=discovery_result,
        max_products_per_category=max_products_per_category,
    )
    llm_result = await _llm_compare_category(
        discovery_result=discovery_result,
        fallback=fallback,
        chat_model=chat_model,
    )
    return llm_result or fallback


def _fallback_compare_category(
    *,
    discovery_result: CategoryDiscoveryResult,
    max_products_per_category: int,
) -> ProductComparison:
    products = _unique_products(discovery_result, max_products=max_products_per_category)
    evaluated: list[ComparedProduct] = []
    for product in products:
        evaluated.append(_evaluate_product(discovery_result.category, discovery_result.goal, product))

    ranked_products = sorted(
        evaluated,
        key=lambda item: (
            -(item.score or 0.0),
            item.monthly_cost if item.monthly_cost is not None else float("inf"),
            item.product.store_domain,
            item.product.title.lower(),
        ),
    )
    ranked_products = [
        product.model_copy(update={"rank": index})
        for index, product in enumerate(ranked_products, start=1)
    ]
    top_pick = ranked_products[0] if ranked_products else None

    summary = "No matching products were found." if not ranked_products else _comparison_summary(
        discovery_result.category,
        ranked_products,
    )
    return ProductComparison(
        category=discovery_result.category,
        goal=discovery_result.goal,
        summary=summary,
        ranked_products=ranked_products,
        top_pick_product_id=top_pick.product.product_id if top_pick else None,
        top_pick_store_domain=top_pick.product.store_domain if top_pick else None,
    )


async def _llm_compare_category(
    *,
    discovery_result: CategoryDiscoveryResult,
    fallback: ProductComparison,
    chat_model: Optional[Any],
) -> Optional[ProductComparison]:
    if chat_model is None or not fallback.ranked_products:
        return None

    evidence = {
        "category": discovery_result.category,
        "goal": discovery_result.goal,
        "candidates": [
            {
                "product": compared_product.product.model_dump(mode="json"),
                "fallback_analysis": compared_product.ingredient_analysis.model_dump(mode="json"),
                "fallback_score": compared_product.score,
                "fallback_monthly_cost": compared_product.monthly_cost,
                "fallback_pros": compared_product.pros,
                "fallback_cons": compared_product.cons,
                "fallback_warnings": compared_product.warnings,
            }
            for compared_product in fallback.ranked_products
        ],
    }

    try:
        response = await invoke_structured(
            chat_model,
            CategoryComparisonDecision,
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(evidence, indent=2, ensure_ascii=True)),
            ],
        )
    except Exception:
        return None

    if response is None or not response.ranked_products:
        return None

    fallback_lookup = {
        (item.product.store_domain, item.product.product_id): item
        for item in fallback.ranked_products
    }
    merged_ranked_products: list[ComparedProduct] = []
    used_keys: set[tuple[str, str]] = set()
    for decision in sorted(response.ranked_products, key=lambda item: (item.rank, item.store_domain, item.product_id)):
        key = (decision.store_domain, decision.product_id)
        fallback_item = fallback_lookup.get(key)
        if fallback_item is None or key in used_keys:
            continue
        merged_ranked_products.append(
            fallback_item.model_copy(
                update={
                    "score": decision.score if decision.score is not None else fallback_item.score,
                    "rationale": decision.rationale or fallback_item.rationale,
                    "pros": decision.pros or fallback_item.pros,
                    "cons": decision.cons or fallback_item.cons,
                    "warnings": decision.warnings or fallback_item.warnings,
                    "ingredient_analysis": decision.ingredient_analysis or fallback_item.ingredient_analysis,
                    "monthly_cost": decision.monthly_cost if decision.monthly_cost is not None else fallback_item.monthly_cost,
                }
            )
        )
        used_keys.add(key)

    for fallback_item in fallback.ranked_products:
        key = (fallback_item.product.store_domain, fallback_item.product.product_id)
        if key not in used_keys:
            merged_ranked_products.append(fallback_item)

    if not merged_ranked_products:
        return None

    normalized_ranked_products = [
        product.model_copy(update={"rank": index})
        for index, product in enumerate(merged_ranked_products, start=1)
    ]
    top_pick = normalized_ranked_products[0]
    return ProductComparison(
        category=fallback.category,
        goal=fallback.goal,
        summary=response.summary or fallback.summary,
        ranked_products=normalized_ranked_products,
        top_pick_product_id=top_pick.product.product_id,
        top_pick_store_domain=top_pick.product.store_domain,
    )


def _unique_products(discovery_result: CategoryDiscoveryResult, *, max_products: int) -> list[ShopifyProduct]:
    deduped: list[ShopifyProduct] = []
    seen_keys: set[tuple[str, str]] = set()
    for store_result in discovery_result.store_results:
        for raw_product in store_result.products:
            product = coerce_shopify_product(raw_product, store_domain=store_result.store_domain)
            key = (product.store_domain, product.product_id)
            if key in seen_keys:
                continue
            deduped.append(product)
            seen_keys.add(key)
            if len(deduped) >= max_products:
                return deduped
    return deduped


def _evaluate_product(category: str, goal: str, product: ShopifyProduct) -> ComparedProduct:
    text = product_text(product)
    dosage_mentions = extract_dosage_mentions(text)
    serving_size, servings_per_container = estimate_serving_details(text)
    price_per_serving = estimate_price_per_serving(product, servings_per_container)
    monthly_cost = estimate_monthly_cost(
        product,
        servings_per_container=servings_per_container,
        price_per_serving=price_per_serving,
    )

    matched_category_terms = matched_keywords(text, category_keywords(category))
    primary_ingredients = [term.title() for term in matched_category_terms] or [product.title]
    bioavailability_notes = extract_bioavailability_notes(text)
    allergens = extract_allergens(text)

    ingredient_analysis = IngredientAnalysis(
        primary_ingredients=primary_ingredients[:4],
        dosage_summary=", ".join(dosage_mentions),
        bioavailability_notes=bioavailability_notes,
        allergens=allergens,
        serving_size=serving_size,
        servings_per_container=servings_per_container,
        price_per_serving=price_per_serving,
        notes=_analysis_notes(dosage_mentions, servings_per_container),
    )

    score = _score_product(
        product=product,
        category=category,
        goal=goal,
        monthly_cost=monthly_cost,
        price_per_serving=price_per_serving,
        matched_category_terms=matched_category_terms,
        bioavailability_notes=bioavailability_notes,
        allergens=allergens,
    )
    pros, cons, warnings = _pros_cons_and_warnings(
        product=product,
        category=category,
        matched_category_terms=matched_category_terms,
        price_per_serving=price_per_serving,
        monthly_cost=monthly_cost,
        bioavailability_notes=bioavailability_notes,
        allergens=allergens,
        dosage_mentions=dosage_mentions,
    )

    rationale_parts = []
    if matched_category_terms:
        rationale_parts.append("Strong ingredient match for {category}".format(category=category))
    if bioavailability_notes:
        rationale_parts.append("helpful form cues in the product details")
    if monthly_cost is not None:
        rationale_parts.append("estimated around ${cost:.2f} per month".format(cost=monthly_cost))
    rationale = ", ".join(rationale_parts) if rationale_parts else "Best available fit from the product payload."

    return ComparedProduct(
        product=product,
        ingredient_analysis=ingredient_analysis,
        rank=1,
        score=score,
        rationale=rationale,
        pros=pros,
        cons=cons,
        warnings=warnings,
        monthly_cost=monthly_cost,
    )


def _analysis_notes(dosage_mentions: list[str], servings_per_container: Optional[float]) -> list[str]:
    notes: list[str] = []
    if not dosage_mentions:
        notes.append("No explicit dosage was detected in the MCP title or description.")
    if servings_per_container is None:
        notes.append("Serving count was not clearly stated in the MCP payload.")
    return notes


def _score_product(
    *,
    product: ShopifyProduct,
    category: str,
    goal: str,
    monthly_cost: Optional[float],
    price_per_serving: Optional[float],
    matched_category_terms: list[str],
    bioavailability_notes: list[str],
    allergens: list[str],
) -> float:
    score = 40.0
    score += len(matched_category_terms) * 8.0
    score += len(bioavailability_notes) * 4.0
    if goal and any(token in product_text(product) for token in goal.lower().split()):
        score += 3.0
    if product.default_variant and product.default_variant.available:
        score += 5.0
    if price_per_serving is not None:
        score += max(0.0, 12.0 - (price_per_serving * 3.0))
    elif monthly_cost is not None:
        score += max(0.0, 10.0 - (monthly_cost / 8.0))
    elif product_price(product) is not None:
        score += max(0.0, 8.0 - (float(product_price(product) or 0.0) / 10.0))
    if allergens:
        score -= 5.0 * len(allergens)
    if not matched_category_terms:
        score -= 8.0
    if category.lower() in {"magnesium", "creatine", "protein powder"} and not bioavailability_notes:
        score -= 2.0
    return round(max(score, 0.0), 2)


def _pros_cons_and_warnings(
    *,
    product: ShopifyProduct,
    category: str,
    matched_category_terms: list[str],
    price_per_serving: Optional[float],
    monthly_cost: Optional[float],
    bioavailability_notes: list[str],
    allergens: list[str],
    dosage_mentions: list[str],
) -> tuple[list[str], list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    warnings: list[str] = []

    if matched_category_terms:
        pros.append("Ingredient profile clearly matches the {category} category.".format(category=category))
    if bioavailability_notes:
        pros.append("Description includes useful form details for comparison.")
    if price_per_serving is not None and price_per_serving <= 1.75:
        pros.append("Competitive estimated price per serving.")
    if monthly_cost is not None and monthly_cost <= 35:
        pros.append("Estimated monthly cost stays moderate.")

    if not dosage_mentions:
        cons.append("Dosage is not clearly stated in the MCP payload.")
    if monthly_cost is not None and monthly_cost >= 60:
        cons.append("Estimated monthly cost is on the high side.")
    if not product.default_variant or not product.default_variant.available:
        cons.append("No clearly available default variant was found.")
    if not matched_category_terms:
        cons.append("Ingredient fit is less explicit than the strongest alternatives.")

    for allergen in allergens:
        warnings.append("Potential {allergen} exposure mentioned in the product details.".format(allergen=allergen))

    return _dedupe_strings(pros), _dedupe_strings(cons), _dedupe_strings(warnings)


def _comparison_summary(category: str, ranked_products: list[ComparedProduct]) -> str:
    top_pick = ranked_products[0]
    if len(ranked_products) == 1:
        return "{title} is the only strong {category} candidate found.".format(
            title=top_pick.product.title,
            category=category,
        )
    runner_up = ranked_products[1]
    return (
        "{top_pick} leads the {category} category on ingredient fit and overall value; "
        "{runner_up} is the main alternative."
    ).format(
        top_pick=top_pick.product.title,
        category=category,
        runner_up=runner_up.product.title,
    )


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
