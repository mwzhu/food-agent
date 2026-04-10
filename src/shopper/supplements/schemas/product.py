from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ShopifyPriceRange(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    currency: str = ""

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("min_price", "max_price", mode="before")
    @classmethod
    def _coerce_prices(cls, value: Any) -> Any:
        return _blank_to_none(value)


class ShopifyProductVariant(BaseModel):
    variant_id: str
    title: str
    price: Optional[float] = None
    currency: str = ""
    available: bool = False
    image_url: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: Any) -> Any:
        return _blank_to_none(value)


class ShopifyProduct(BaseModel):
    store_domain: str
    product_id: str
    title: str
    description: str = ""
    url: str
    image_url: Optional[str] = None
    image_alt_text: Optional[str] = None
    product_type: str = ""
    tags: list[str] = Field(default_factory=list)
    price_range: ShopifyPriceRange = Field(default_factory=ShopifyPriceRange)
    variants: list[ShopifyProductVariant] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @property
    def default_variant(self) -> Optional[ShopifyProductVariant]:
        for variant in self.variants:
            if variant.available:
                return variant
        return self.variants[0] if self.variants else None

    @classmethod
    def from_mcp(cls, *, store_domain: str, product: Any) -> "ShopifyProduct":
        price_range = getattr(product, "price_range", None)
        variants = getattr(product, "variants", []) or []
        return cls(
            store_domain=store_domain,
            product_id=getattr(product, "product_id", ""),
            title=getattr(product, "title", ""),
            description=getattr(product, "description", ""),
            url=getattr(product, "url", ""),
            image_url=getattr(product, "image_url", None),
            image_alt_text=getattr(product, "image_alt_text", None),
            product_type=getattr(product, "product_type", ""),
            tags=list(getattr(product, "tags", []) or []),
            price_range=ShopifyPriceRange(
                min_price=getattr(price_range, "min_price", None),
                max_price=getattr(price_range, "max_price", None),
                currency=getattr(price_range, "currency", ""),
            ),
            variants=[
                ShopifyProductVariant(
                    variant_id=getattr(variant, "variant_id", ""),
                    title=getattr(variant, "title", ""),
                    price=getattr(variant, "price", None),
                    currency=getattr(variant, "currency", ""),
                    available=bool(getattr(variant, "available", False)),
                    image_url=getattr(variant, "image_url", None),
                )
                for variant in variants
            ],
        )


class StoreSearchResult(BaseModel):
    store_domain: str
    query: str
    products: list[ShopifyProduct] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)


class CategoryDiscoveryResult(BaseModel):
    category: str
    goal: str
    search_queries: list[str] = Field(default_factory=list)
    store_results: list[StoreSearchResult] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)


class IngredientAnalysis(BaseModel):
    primary_ingredients: list[str] = Field(default_factory=list)
    dosage_summary: str = ""
    bioavailability_notes: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    serving_size: Optional[str] = None
    servings_per_container: Optional[float] = None
    price_per_serving: Optional[float] = None
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("servings_per_container", "price_per_serving", mode="before")
    @classmethod
    def _coerce_optional_numbers(cls, value: Any) -> Any:
        return _blank_to_none(value)


class ComparedProduct(BaseModel):
    product: ShopifyProduct
    ingredient_analysis: IngredientAnalysis = Field(default_factory=IngredientAnalysis)
    rank: int = Field(default=1, ge=1)
    score: Optional[float] = Field(default=None, ge=0)
    rationale: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    monthly_cost: Optional[float] = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("monthly_cost", mode="before")
    @classmethod
    def _coerce_monthly_cost(cls, value: Any) -> Any:
        return _blank_to_none(value)


class ProductComparison(BaseModel):
    category: str
    goal: str
    summary: str = ""
    ranked_products: list[ComparedProduct] = Field(default_factory=list)
    top_pick_product_id: Optional[str] = None
    top_pick_store_domain: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)
