from __future__ import annotations

import asyncio

from shopper.supplements.agents.nodes import (
    health_goal_analyzer,
    ingredient_comparator,
    mcp_cart_builder,
    stack_builder,
    store_searcher,
    supplement_critic,
)
from shopper.supplements.schemas import (
    CategoryDiscoveryResult,
    ComparedProduct,
    HealthProfile,
    IngredientAnalysis,
    ProductComparison,
    ShopifyPriceRange,
    ShopifyProduct,
    ShopifyProductVariant,
    StackItem,
    StoreCart,
    StoreSearchResult,
    SupplementCriticVerdict,
    SupplementNeed,
    SupplementStack,
)
from shopper.supplements.tools.shopify_mcp import ShopifyCartLine as MCPShopifyCartLine
from shopper.supplements.tools.shopify_mcp import ShopifyCartResult as MCPShopifyCartResult


def _health_profile(**overrides) -> HealthProfile:
    payload = {
        "age": 34,
        "weight_lbs": 175,
        "sex": "male",
        "health_goals": ["better sleep"],
        "current_supplements": [],
        "medications": [],
        "conditions": [],
        "allergies": [],
        "monthly_budget": 100,
    }
    payload.update(overrides)
    return HealthProfile.model_validate(payload)


def _product(
    *,
    store_domain: str,
    product_id: str,
    title: str,
    price: float,
    description: str = "",
    variant_id: str | None = None,
    tags: list[str] | None = None,
) -> ShopifyProduct:
    variant_identifier = variant_id or "{product_id}-variant".format(product_id=product_id)
    return ShopifyProduct(
        store_domain=store_domain,
        product_id=product_id,
        title=title,
        description=description,
        url="https://{store}/products/{product}".format(store=store_domain, product=product_id),
        image_url=None,
        image_alt_text=None,
        product_type="Supplement",
        tags=tags or [],
        price_range=ShopifyPriceRange(min_price=price, max_price=price, currency="USD"),
        variants=[
            ShopifyProductVariant(
                variant_id=variant_identifier,
                title="Default Title",
                price=price,
                currency="USD",
                available=True,
                image_url=None,
            )
        ],
    )


def _compared_product(
    *,
    product: ShopifyProduct,
    rank: int,
    monthly_cost: float,
    rationale: str,
    category_keyword: str,
    goal: str,
    allergens: list[str] | None = None,
) -> ComparedProduct:
    return ComparedProduct(
        product=product,
        ingredient_analysis=IngredientAnalysis(
            primary_ingredients=[category_keyword.title()],
            dosage_summary="1 serving",
            bioavailability_notes=[],
            allergens=allergens or [],
            serving_size="1 serving",
            servings_per_container=30,
            price_per_serving=round(monthly_cost / 30, 2),
            notes=[],
        ),
        rank=rank,
        score=100 - (rank * 5),
        rationale=rationale,
        pros=["Good fit for {goal}".format(goal=goal)],
        cons=[],
        warnings=[],
        monthly_cost=monthly_cost,
    )


def test_health_goal_analyzer_skips_existing_supplements_and_uses_fallback_rules():
    state = {
        "run_id": "supp-run",
        "health_profile": _health_profile(
            health_goals=["better sleep", "muscle recovery"],
            current_supplements=["Creatine Monohydrate"],
        ).model_dump(mode="json"),
    }

    result = asyncio.run(health_goal_analyzer(state))

    categories = [need["category"] for need in result["identified_needs"]]
    assert categories == ["magnesium", "protein powder"]
    assert all(need["search_queries"] for need in result["identified_needs"])


def test_store_searcher_groups_results_by_category_and_store():
    calls: list[tuple[str, str]] = []

    async def fake_search_store(store_domain: str, query: str):
        calls.append((store_domain, query))
        return [
            _product(
                store_domain=store_domain,
                product_id="{store}-{query}".format(store=store_domain, query=query.replace(" ", "-")),
                title="{query} {store}".format(query=query.title(), store=store_domain),
                price=29.0,
                description="30 servings",
            )
        ]

    state = {
        "run_id": "supp-run",
        "identified_needs": [
            SupplementNeed(
                category="magnesium",
                goal="better sleep",
                rationale="",
                search_queries=["magnesium", "sleep magnesium"],
                priority=1,
            ).model_dump(mode="json")
        ],
    }

    result = asyncio.run(
        store_searcher(
            state,
            search_store_fn=fake_search_store,
            store_domains=("ritual.com", "transparentlabs.com"),
        )
    )

    discovery_results = [CategoryDiscoveryResult.model_validate(item) for item in result["discovery_results"]]
    assert len(calls) == 4
    assert len(discovery_results) == 1
    assert len(discovery_results[0].store_results) == 4
    assert {store_result.store_domain for store_result in discovery_results[0].store_results} == {
        "ritual.com",
        "transparentlabs.com",
    }


def test_ingredient_comparator_ranks_best_category_match_first():
    discovery_result = CategoryDiscoveryResult(
        category="magnesium",
        goal="better sleep",
        search_queries=["magnesium"],
        store_results=[
            StoreSearchResult(
                store_domain="livemomentous.com",
                query="magnesium",
                products=[
                    _product(
                        store_domain="livemomentous.com",
                        product_id="magnesium-l-threonate",
                        title="Magnesium L-Threonate",
                        price=45.0,
                        description="144 mg magnesium per serving. 30 servings. L-threonate form.",
                    )
                ],
            ),
            StoreSearchResult(
                store_domain="ritual.com",
                query="magnesium",
                products=[
                    _product(
                        store_domain="ritual.com",
                        product_id="sleep-gummies",
                        title="Sleep Gummies",
                        price=39.0,
                        description="3 mg melatonin. 60 gummies.",
                    )
                ],
            ),
        ],
    )

    result = asyncio.run(
        ingredient_comparator(
            {
                "run_id": "supp-run",
                "discovery_results": [discovery_result.model_dump(mode="json")],
            }
        )
    )

    comparison = ProductComparison.model_validate(result["product_comparisons"][0])
    assert comparison.top_pick_product_id == "magnesium-l-threonate"
    assert comparison.ranked_products[0].ingredient_analysis.price_per_serving == 1.5
    assert "Magnesium" in comparison.ranked_products[0].ingredient_analysis.primary_ingredients


def test_stack_builder_swaps_to_lower_cost_alternative_to_fit_budget():
    magnesium_expensive = _product(
        store_domain="livemomentous.com",
        product_id="magnesium-premium",
        title="Premium Magnesium",
        price=50.0,
        description="30 servings.",
    )
    magnesium_budget = _product(
        store_domain="ritual.com",
        product_id="magnesium-budget",
        title="Budget Magnesium",
        price=25.0,
        description="30 servings.",
    )
    creatine = _product(
        store_domain="transparentlabs.com",
        product_id="creatine-best",
        title="Creatine HMB",
        price=20.0,
        description="30 servings.",
    )

    comparisons = [
        ProductComparison(
            category="magnesium",
            goal="better sleep",
            summary="",
            ranked_products=[
                _compared_product(
                    product=magnesium_expensive,
                    rank=1,
                    monthly_cost=50.0,
                    rationale="Best form quality.",
                    category_keyword="magnesium",
                    goal="better sleep",
                ),
                _compared_product(
                    product=magnesium_budget,
                    rank=2,
                    monthly_cost=25.0,
                    rationale="Lower-cost backup.",
                    category_keyword="magnesium",
                    goal="better sleep",
                ),
            ],
            top_pick_product_id="magnesium-premium",
            top_pick_store_domain="livemomentous.com",
        ),
        ProductComparison(
            category="creatine",
            goal="muscle recovery",
            summary="",
            ranked_products=[
                _compared_product(
                    product=creatine,
                    rank=1,
                    monthly_cost=20.0,
                    rationale="Established recovery option.",
                    category_keyword="creatine",
                    goal="muscle recovery",
                )
            ],
            top_pick_product_id="creatine-best",
            top_pick_store_domain="transparentlabs.com",
        ),
    ]

    result = asyncio.run(
        stack_builder(
            {
                "run_id": "supp-run",
                "health_profile": _health_profile(
                    health_goals=["better sleep", "muscle recovery"],
                    monthly_budget=45,
                ).model_dump(mode="json"),
                "identified_needs": [
                    SupplementNeed(
                        category="magnesium",
                        goal="better sleep",
                        rationale="",
                        search_queries=["magnesium"],
                        priority=1,
                    ).model_dump(mode="json"),
                    SupplementNeed(
                        category="creatine",
                        goal="muscle recovery",
                        rationale="",
                        search_queries=["creatine"],
                        priority=2,
                    ).model_dump(mode="json"),
                ],
                "product_comparisons": [comparison.model_dump(mode="json") for comparison in comparisons],
            }
        )
    )

    stack = SupplementStack.model_validate(result["recommended_stack"])
    assert stack.within_budget is True
    assert stack.total_monthly_cost == 45.0
    assert {item.product.product_id for item in stack.items} == {"magnesium-budget", "creatine-best"}


def test_supplement_critic_requests_manual_review_when_medications_are_present():
    product = _product(
        store_domain="livemomentous.com",
        product_id="magnesium-l-threonate",
        title="Magnesium L-Threonate",
        price=45.0,
        description="30 servings.",
    )
    comparison = ProductComparison(
        category="magnesium",
        goal="better sleep",
        summary="",
        ranked_products=[
            _compared_product(
                product=product,
                rank=1,
                monthly_cost=45.0,
                rationale="Strong sleep-support match.",
                category_keyword="magnesium",
                goal="better sleep",
            )
        ],
        top_pick_product_id=product.product_id,
        top_pick_store_domain=product.store_domain,
    )
    stack = SupplementStack(
        summary="",
        items=[
            StackItem(
                category="magnesium",
                goal="better sleep",
                product=product,
                quantity=1,
                dosage="1 serving",
                cadence="Daily",
                monthly_cost=45.0,
                rationale="Strong sleep-support match.",
                cautions=[],
            )
        ],
        total_monthly_cost=45.0,
        currency="USD",
        within_budget=True,
        notes=[],
        warnings=[],
    )

    result = asyncio.run(
        supplement_critic(
            {
                "run_id": "supp-run",
                "health_profile": _health_profile(
                    medications=["Sertraline"],
                    monthly_budget=60,
                ).model_dump(mode="json"),
                "product_comparisons": [comparison.model_dump(mode="json")],
                "recommended_stack": stack.model_dump(mode="json"),
            }
        )
    )

    verdict = SupplementCriticVerdict.model_validate(result["critic_verdict"])
    assert verdict.decision == "manual_review_needed"
    assert verdict.manual_review_reason is not None


def test_supplement_critic_fails_when_stack_conflicts_with_allergy():
    product = _product(
        store_domain="transparentlabs.com",
        product_id="whey-isolate",
        title="Grass-Fed Whey Isolate",
        price=45.0,
        description="Milk-derived protein isolate. 30 servings.",
    )
    comparison = ProductComparison(
        category="protein powder",
        goal="muscle recovery",
        summary="",
        ranked_products=[
            _compared_product(
                product=product,
                rank=1,
                monthly_cost=45.0,
                rationale="Protein-first recovery option.",
                category_keyword="protein",
                goal="muscle recovery",
                allergens=["dairy"],
            )
        ],
        top_pick_product_id=product.product_id,
        top_pick_store_domain=product.store_domain,
    )
    stack = SupplementStack(
        summary="",
        items=[
            StackItem(
                category="protein powder",
                goal="muscle recovery",
                product=product,
                quantity=1,
                dosage="1 serving",
                cadence="Daily",
                monthly_cost=45.0,
                rationale="Protein-first recovery option.",
                cautions=[],
            )
        ],
        total_monthly_cost=45.0,
        currency="USD",
        within_budget=True,
        notes=[],
        warnings=[],
    )

    result = asyncio.run(
        supplement_critic(
            {
                "run_id": "supp-run",
                "health_profile": _health_profile(
                    health_goals=["muscle recovery"],
                    allergies=["dairy"],
                    monthly_budget=80,
                ).model_dump(mode="json"),
                "product_comparisons": [comparison.model_dump(mode="json")],
                "recommended_stack": stack.model_dump(mode="json"),
            }
        )
    )

    verdict = SupplementCriticVerdict.model_validate(result["critic_verdict"])
    assert verdict.decision == "failed"
    assert any("dairy" in issue.lower() for issue in verdict.issues)


def test_mcp_cart_builder_groups_items_by_store_and_reuses_cart_id():
    store_state: dict[str, dict] = {}

    async def fake_update_cart(store_domain: str, variant_id: str, quantity: int, *, cart_id=None):
        current = store_state.setdefault(
            store_domain,
            {
                "cart_id": "{store}-cart".format(store=store_domain),
                "checkout_url": "https://{store}/cart".format(store=store_domain),
                "lines": [],
            },
        )
        if cart_id is not None:
            assert cart_id == current["cart_id"]

        current["lines"].append(
            MCPShopifyCartLine(
                line_id="line-{count}".format(count=len(current["lines"]) + 1),
                quantity=quantity,
                product_title="Product {variant}".format(variant=variant_id),
                product_id="product-{variant}".format(variant=variant_id),
                variant_id=variant_id,
                variant_title="Default Title",
                subtotal_amount=str(10 * quantity),
                total_amount=str(10 * quantity),
                currency="USD",
            )
        )
        total_quantity = sum(line.quantity for line in current["lines"])
        total_amount = str(sum(float(line.total_amount or 0) for line in current["lines"]))
        return MCPShopifyCartResult(
            store_domain=store_domain,
            cart_id=current["cart_id"],
            checkout_url=current["checkout_url"],
            created_at="2026-04-09T00:00:00Z",
            updated_at="2026-04-09T00:00:00Z",
            total_quantity=total_quantity,
            subtotal_amount=total_amount,
            total_amount=total_amount,
            currency="USD",
            lines=list(current["lines"]),
            errors=[],
            instructions="Open the checkout URL.",
        )

    ritual_one = _product(
        store_domain="ritual.com",
        product_id="ritual-sleep",
        title="Ritual Sleep",
        price=20.0,
        variant_id="ritual-1",
    )
    ritual_two = _product(
        store_domain="ritual.com",
        product_id="ritual-multi",
        title="Ritual Multi",
        price=20.0,
        variant_id="ritual-2",
    )
    transparent = _product(
        store_domain="transparentlabs.com",
        product_id="transparent-creatine",
        title="Transparent Creatine",
        price=20.0,
        variant_id="transparent-1",
    )
    stack = SupplementStack(
        summary="",
        items=[
            StackItem(
                category="magnesium",
                goal="better sleep",
                product=ritual_one,
                quantity=1,
                dosage="1 serving",
                cadence="Daily",
                monthly_cost=20.0,
                rationale="",
                cautions=[],
            ),
            StackItem(
                category="multivitamin",
                goal="wellness",
                product=ritual_two,
                quantity=1,
                dosage="1 serving",
                cadence="Daily",
                monthly_cost=20.0,
                rationale="",
                cautions=[],
            ),
            StackItem(
                category="creatine",
                goal="muscle recovery",
                product=transparent,
                quantity=2,
                dosage="1 serving",
                cadence="Daily",
                monthly_cost=40.0,
                rationale="",
                cautions=[],
            ),
        ],
        total_monthly_cost=80.0,
        currency="USD",
        within_budget=True,
        notes=[],
        warnings=[],
    )

    result = asyncio.run(
        mcp_cart_builder(
            {
                "run_id": "supp-run",
                "recommended_stack": stack.model_dump(mode="json"),
            },
            update_cart_fn=fake_update_cart,
        )
    )

    carts = [StoreCart.model_validate(item) for item in result["store_carts"]]
    assert len(carts) == 2
    ritual_cart = next(cart for cart in carts if cart.store_domain == "ritual.com")
    transparent_cart = next(cart for cart in carts if cart.store_domain == "transparentlabs.com")
    assert ritual_cart.total_quantity == 2
    assert len(ritual_cart.lines) == 2
    assert transparent_cart.total_quantity == 2
