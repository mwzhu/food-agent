from __future__ import annotations

import re
from typing import Any, Optional

from shopper.supplements.schemas import ShopifyProduct, StoreCart


DEFAULT_VERIFIED_STORE_DOMAINS = (
    "ritual.com",
    "transparentlabs.com",
    "livemomentous.com",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "adaptogen": ("ashwagandha", "adaptogen", "rhodiola"),
    "collagen": ("collagen", "peptides"),
    "creatine": ("creatine", "monohydrate", "hmb"),
    "electrolytes": ("electrolyte", "hydration", "sodium", "potassium"),
    "magnesium": ("magnesium", "glycinate", "bisglycinate", "threonate"),
    "melatonin": ("melatonin",),
    "multivitamin": ("multivitamin", "daily", "essential", "women", "men"),
    "omega-3": ("omega-3", "omega 3", "dha", "epa", "fish oil"),
    "probiotic": ("probiotic", "prebiotic", "digestive", "gut"),
    "protein powder": ("protein", "whey", "isolate", "casein", "powder"),
    "vitamin d": ("vitamin d", "d3", "k2"),
}

ALLERGEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dairy": ("dairy", "milk", "whey", "casein"),
    "egg": ("egg", "albumin"),
    "fish": ("fish", "anchovy", "sardine", "salmon"),
    "gluten": ("gluten", "wheat"),
    "peanut": ("peanut",),
    "sesame": ("sesame",),
    "shellfish": ("shellfish", "shrimp", "crab", "lobster"),
    "soy": ("soy", "soybean"),
    "tree nuts": ("almond", "cashew", "coconut", "macadamia", "pecan", "pistachio", "walnut"),
}

BIOAVAILABILITY_HINTS: dict[str, str] = {
    "bisglycinate": "Chelated bisglycinate form is often chosen for gentler magnesium support.",
    "glycinate": "Glycinate form is commonly used for calmer magnesium support.",
    "hmb": "HMB pairing is often positioned for recovery-focused creatine formulas.",
    "isolate": "Isolate formulas usually reduce extra carbs and fats per serving.",
    "l-threonate": "L-threonate form is frequently marketed for magnesium brain and sleep support.",
    "liposomal": "Liposomal delivery is marketed for improved absorption.",
    "methylated": "Methylated forms can be useful when a brand emphasizes active B vitamins.",
    "monohydrate": "Monohydrate remains the most established creatine form.",
    "triglyceride": "Triglyceride-form fish oil is commonly treated as a quality signal.",
}

DOSAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu)", re.IGNORECASE)
SERVING_SIZE_PATTERN = re.compile(
    r"(?:serving size|take)\D{0,10}(\d+(?:\.\d+)?)\s*(capsules?|tablets?|softgels?|gummies|scoops?|packets?|sticks?)",
    re.IGNORECASE,
)
CONTAINER_COUNT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(servings?|capsules?|tablets?|softgels?|gummies|packets?|sticks?)",
    re.IGNORECASE,
)


def normalize_text(*parts: Any) -> str:
    return " ".join(str(part).strip().lower() for part in parts if part).strip()


def category_keywords(category: str) -> set[str]:
    normalized = category.strip().lower()
    keywords = set(CATEGORY_KEYWORDS.get(normalized, ()))
    keywords.update(token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1)
    return keywords


def coerce_shopify_product(product: Any, *, store_domain: Optional[str] = None) -> ShopifyProduct:
    if isinstance(product, ShopifyProduct):
        return product
    if hasattr(product, "product_id"):
        resolved_store_domain = store_domain or getattr(product, "store_domain", "")
        return ShopifyProduct.from_mcp(store_domain=resolved_store_domain, product=product)
    return ShopifyProduct.model_validate(product)


def coerce_store_cart(cart: Any) -> StoreCart:
    if isinstance(cart, StoreCart):
        return cart
    if hasattr(cart, "checkout_url") or hasattr(cart, "cart_id"):
        return StoreCart.from_mcp(cart)
    return StoreCart.model_validate(cart)


def product_text(product: ShopifyProduct) -> str:
    return normalize_text(product.title, product.description, product.product_type, " ".join(product.tags))


def product_price(product: ShopifyProduct) -> Optional[float]:
    if product.default_variant and product.default_variant.price is not None:
        return float(product.default_variant.price)
    if product.price_range.min_price is not None:
        return float(product.price_range.min_price)
    for variant in product.variants:
        if variant.price is not None:
            return float(variant.price)
    return None


def product_currency(product: ShopifyProduct) -> str:
    if product.default_variant and product.default_variant.currency:
        return product.default_variant.currency
    if product.price_range.currency:
        return product.price_range.currency
    for variant in product.variants:
        if variant.currency:
            return variant.currency
    return "USD"


def matched_keywords(text: str, keywords: set[str]) -> list[str]:
    found: list[str] = []
    for keyword in keywords:
        if keyword and keyword in text and keyword not in found:
            found.append(keyword)
    return found


def extract_dosage_mentions(text: str) -> list[str]:
    seen: set[str] = set()
    matches: list[str] = []
    for amount, unit in DOSAGE_PATTERN.findall(text):
        rendered = "{amount} {unit}".format(amount=amount, unit=unit.lower())
        if rendered not in seen:
            matches.append(rendered)
            seen.add(rendered)
        if len(matches) >= 3:
            break
    return matches


def estimate_serving_details(text: str) -> tuple[Optional[str], Optional[float]]:
    serving_size_match = SERVING_SIZE_PATTERN.search(text)
    serving_size: Optional[str] = None
    serving_units: Optional[float] = None
    serving_unit_label: Optional[str] = None
    if serving_size_match:
        serving_units = float(serving_size_match.group(1))
        serving_unit_label = serving_size_match.group(2).lower()
        serving_size = "{amount} {label}".format(amount=serving_size_match.group(1), label=serving_unit_label)

    for count_match in CONTAINER_COUNT_PATTERN.finditer(text):
        count_value = float(count_match.group(1))
        count_label = count_match.group(2).lower()
        if "serving" in count_label:
            return serving_size, count_value
        if serving_units and serving_unit_label and count_label.rstrip("s") == serving_unit_label.rstrip("s"):
            return serving_size, round(count_value / serving_units, 2)
        return serving_size, count_value
    return serving_size, None


def extract_bioavailability_notes(text: str) -> list[str]:
    notes: list[str] = []
    for keyword, note in BIOAVAILABILITY_HINTS.items():
        if keyword in text:
            notes.append(note)
    return notes


def extract_allergens(text: str) -> list[str]:
    allergens: list[str] = []
    for allergen, keywords in ALLERGEN_KEYWORDS.items():
        for keyword in keywords:
            if keyword not in text:
                continue
            if any(
                phrase in text
                for phrase in (
                    "{keyword}-free".format(keyword=keyword),
                    "{keyword} free".format(keyword=keyword),
                    "free of {keyword}".format(keyword=keyword),
                )
            ):
                continue
            allergens.append(allergen)
            break
    return allergens


def estimate_price_per_serving(product: ShopifyProduct, servings_per_container: Optional[float]) -> Optional[float]:
    price = product_price(product)
    if price is None or servings_per_container is None or servings_per_container <= 0:
        return None
    return round(price / servings_per_container, 2)


def estimate_monthly_cost(
    product: ShopifyProduct,
    *,
    servings_per_container: Optional[float] = None,
    price_per_serving: Optional[float] = None,
    servings_per_month: int = 30,
) -> Optional[float]:
    if price_per_serving is not None:
        return round(price_per_serving * servings_per_month, 2)
    price = product_price(product)
    if price is None:
        return None
    if servings_per_container and servings_per_container < servings_per_month:
        return round((servings_per_month / servings_per_container) * price, 2)
    return round(price, 2)


def category_already_covered(category: str, supplement_names: list[str]) -> bool:
    supplement_text = normalize_text(" ".join(supplement_names))
    return bool(matched_keywords(supplement_text, category_keywords(category)))
