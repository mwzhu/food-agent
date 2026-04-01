from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shopper.schemas import RecipeRecord


MEAL_TYPES: Tuple[str, ...] = ("breakfast", "lunch", "dinner", "snack")
DEFAULT_TARGET_MEAL_COUNTS: Mapping[str, int] = {
    "breakfast": 400,
    "lunch": 500,
    "dinner": 700,
    "snack": 400,
}
MAX_BUCKET_SIZE = 160
PRUNE_BUCKET_AT = MAX_BUCKET_SIZE * 3
PROGRESS_EVERY = 100000
MAX_PREP_TIME_MIN = 75
MIN_CALORIES_BY_MEAL: Mapping[str, int] = {
    "breakfast": 220,
    "lunch": 280,
    "dinner": 320,
    "snack": 120,
}
MAX_CALORIES_BY_MEAL: Mapping[str, int] = {
    "breakfast": 650,
    "lunch": 800,
    "dinner": 900,
    "snack": 420,
}
UNIT_ALIASES: Mapping[str, str] = {
    "c": "cup",
    "cup": "cup",
    "cups": "cup",
    "t": "tbsp",
    "tb": "tbsp",
    "tbl": "tbsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "pkg": "package",
    "pkgs": "package",
    "package": "package",
    "packages": "package",
    "pack": "package",
    "packs": "package",
    "box": "package",
    "boxes": "package",
    "jar": "jar",
    "jars": "jar",
    "can": "can",
    "cans": "can",
    "clove": "clove",
    "cloves": "clove",
    "slice": "slice",
    "slices": "slice",
    "breast": "breast",
    "breasts": "breast",
    "thigh": "piece",
    "thighs": "piece",
    "piece": "piece",
    "pieces": "piece",
    "fillet": "piece",
    "fillets": "piece",
    "stick": "stick",
    "sticks": "stick",
    "loaf": "loaf",
    "loaves": "loaf",
    "head": "head",
    "heads": "head",
    "bunch": "bunch",
    "bunches": "bunch",
}
UNICODE_FRACTIONS: Mapping[str, str] = {
    "1/4": "1/4",
    "1/2": "1/2",
    "3/4": "3/4",
}
RAW_UNICODE_FRACTIONS: Mapping[str, str] = {
    "¼": " 1/4",
    "½": " 1/2",
    "¾": " 3/4",
    "⅓": " 1/3",
    "⅔": " 2/3",
    "⅛": " 1/8",
}
COOKING_VERBS = (
    "bake",
    "boil",
    "cook",
    "grill",
    "roast",
    "saute",
    "simmer",
    "broil",
    "fry",
    "microwave",
    "steam",
)
PASSIVE_TIME_VERBS = (
    "bake",
    "roast",
    "refrigerate",
    "chill",
    "marinate",
    "freeze",
    "slow cook",
    "slow-cook",
    "simmer",
)
BREAKFAST_KEYWORDS = (
    "breakfast",
    "brunch",
    "oatmeal",
    "overnight oat",
    "granola",
    "pancake",
    "waffle",
    "omelet",
    "omelette",
    "frittata",
    "scramble",
    "breakfast burrito",
    "yogurt",
    "parfait",
    "smoothie",
    "bagel",
    "toast",
    "breakfast casserole",
    "muffin",
    "scone",
    "cereal",
    "hash brown",
)
SNACK_KEYWORDS = (
    "appetizer",
    "dip",
    "salsa",
    "hummus",
    "snack",
    "trail mix",
    "popcorn",
    "granola bar",
    "energy bite",
    "fruit cup",
    "fruit salad",
    "deviled egg",
    "bruschetta",
    "cracker",
)
LUNCH_KEYWORDS = (
    "salad",
    "sandwich",
    "wrap",
    "melt",
    "burger",
    "slaw",
    "soup",
    "chowder",
    "bisque",
    "quesadilla",
    "panini",
    "pita",
    "bowl",
)
DINNER_KEYWORDS = (
    "casserole",
    "lasagna",
    "enchilada",
    "stew",
    "roast",
    "skillet",
    "meatloaf",
    "stir fry",
    "stir-fry",
    "curry",
    "pasta",
    "risotto",
    "fajita",
    "pot pie",
    "roasted",
)
PROTEIN_HINTS = (
    "chicken",
    "beef",
    "steak",
    "pork",
    "salmon",
    "shrimp",
    "turkey",
    "tofu",
    "lentil",
    "bean",
    "sausage",
)
STRONG_DESSERT_KEYWORDS = (
    "dessert",
    "cookie",
    "cake",
    "brownie",
    "fudge",
    "candy",
    "icing",
    "frosting",
    "pie",
    "cobbler",
    "pudding",
    "gelatin",
    "jello",
    "cheesecake",
    "mousse",
    "cupcake",
    "truffle",
    "toffee",
    "sherbet",
    "ice cream",
    "milkshake",
    "torte",
)
WEAK_DESSERT_TITLE_KEYWORDS = (
    "delight",
    "fluff",
    "shortcake",
    "cobbler",
    "pudding",
)
CONDIMENT_KEYWORDS = (
    "dressing",
    "marinade",
    "seasoning",
    "rub",
    "relish",
    "jam",
    "jelly",
    "preserve",
    "syrup",
    "gravy",
    "frosting",
    "icing",
    "sauce",
)
BEVERAGE_KEYWORDS = (
    "cocktail",
    "punch",
    "lemonade",
    "tea",
    "coffee",
    "latte",
    "soda",
    "martini",
    "margarita",
)
APPETIZER_KEYWORDS = (
    "dip",
    "salsa",
    "hummus",
    "wings",
    "pinwheel",
    "roll-up",
    "roll up",
    "bruschetta",
    "skewer",
)
MEAT_KEYWORDS = (
    "beef",
    "steak",
    "ground beef",
    "chicken",
    "turkey",
    "duck",
    "pork",
    "ham",
    "bacon",
    "sausage",
    "salami",
    "pepperoni",
    "lamb",
    "veal",
    "fish",
    "salmon",
    "tuna",
    "cod",
    "tilapia",
    "trout",
    "halibut",
    "haddock",
    "mahi",
    "shrimp",
    "prawn",
    "crab",
    "lobster",
    "clam",
    "oyster",
    "scallop",
    "anchovy",
    "sardine",
)
DAIRY_KEYWORDS = (
    "milk",
    "butter",
    "cheese",
    "cream",
    "half and half",
    "half-and-half",
    "sour cream",
    "yogurt",
    "yoghurt",
    "ricotta",
    "parmesan",
    "mozzarella",
    "cheddar",
    "feta",
    "cream cheese",
    "evaporated milk",
    "condensed milk",
)
EGG_KEYWORDS = ("egg", "eggs", "mayonnaise", "mayo")
GLUTEN_KEYWORDS = (
    "flour",
    "bread",
    "bun",
    "roll",
    "pasta",
    "spaghetti",
    "macaroni",
    "noodle",
    "cracker",
    "biscuit",
    "breadcrumb",
    "breadcrumbs",
    "cake mix",
    "brownie mix",
    "pie crust",
)
HONEY_GELATIN_KEYWORDS = ("honey", "gelatin")
PROTEIN_TAG_THRESHOLD = 25


@dataclass(frozen=True)
class NutritionProfile:
    calories: float
    protein: float
    carbs: float
    fat: float
    unit_multipliers: Mapping[str, float] = field(default_factory=dict)


@dataclass
class CorpusCandidate:
    dedupe_key: str
    primary_meal_type: str
    cuisine: str
    quality_score: float
    tiebreak: str
    payload: Dict[str, Any]


@dataclass
class BuildSummary:
    target_count: int
    selected_count: int
    processed_rows: int
    eligible_rows: int
    skipped_rows: int
    output_path: str
    source_path: str
    meal_type_counts: Dict[str, int]
    cuisine_counts: Dict[str, int]
    tag_counts: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_count": self.target_count,
            "selected_count": self.selected_count,
            "processed_rows": self.processed_rows,
            "eligible_rows": self.eligible_rows,
            "skipped_rows": self.skipped_rows,
            "output_path": self.output_path,
            "source_path": self.source_path,
            "meal_type_counts": self.meal_type_counts,
            "cuisine_counts": self.cuisine_counts,
            "tag_counts": self.tag_counts,
        }


NUTRITION_PROFILES: Sequence[Tuple[Tuple[str, ...], NutritionProfile]] = (
    (("chicken breast",), NutritionProfile(140, 26, 0, 3, {"lb": 4, "oz": 0.25, "breast": 1, "cup": 2, "piece": 1, "package": 4})),
    (("ground chicken", "chicken thighs", "chicken thigh", "chicken"), NutritionProfile(165, 24, 0, 7, {"lb": 4, "oz": 0.25, "piece": 1, "cup": 2, "package": 4})),
    (("ground turkey", "turkey breast", "turkey"), NutritionProfile(145, 24, 0, 5, {"lb": 4, "oz": 0.25, "piece": 1, "cup": 2, "package": 4})),
    (("ground beef",), NutritionProfile(290, 19, 0, 23, {"lb": 4, "oz": 0.25, "package": 4})),
    (("beef", "steak", "roast"), NutritionProfile(230, 22, 0, 14, {"lb": 4, "oz": 0.25, "piece": 1, "cup": 2})),
    (("pork", "ham", "sausage", "bacon"), NutritionProfile(220, 18, 1, 16, {"lb": 4, "oz": 0.25, "piece": 1, "slice": 0.5, "package": 4})),
    (("salmon", "tuna", "fish", "tilapia", "cod"), NutritionProfile(160, 24, 0, 6, {"lb": 4, "oz": 0.25, "piece": 1, "can": 2})),
    (("shrimp", "prawn", "crab", "lobster", "scallop"), NutritionProfile(120, 23, 1, 2, {"lb": 4, "oz": 0.25, "cup": 2, "package": 4})),
    (("egg", "eggs"), NutritionProfile(70, 6, 1, 5, {"piece": 1, "package": 6, "cup": 4})),
    (("tofu", "tempeh"), NutritionProfile(90, 10, 3, 5, {"oz": 0.33, "package": 4, "cup": 2, "piece": 1})),
    (("black bean", "kidney bean", "pinto bean", "garbanzo", "chickpea", "lentil", "bean"), NutritionProfile(120, 7, 20, 1, {"cup": 2, "can": 3.5, "tbsp": 0.125, "oz": 0.25})),
    (("rice",), NutritionProfile(340, 7, 75, 1, {"cup": 2, "tbsp": 0.125, "oz": 0.25, "lb": 4.5})),
    (("pasta", "macaroni", "spaghetti", "noodle"), NutritionProfile(200, 7, 40, 1, {"oz": 1, "cup": 1, "lb": 8, "package": 8})),
    (("oat", "oats"), NutritionProfile(150, 5, 27, 3, {"cup": 2, "tbsp": 0.125, "package": 6})),
    (("bread", "bun", "bagel", "roll", "toast"), NutritionProfile(160, 6, 30, 2, {"slice": 0.5, "piece": 1, "loaf": 10, "package": 8})),
    (("tortilla", "wrap", "pita"), NutritionProfile(140, 4, 24, 4, {"piece": 1, "package": 8})),
    (("potato", "sweet potato", "hash brown"), NutritionProfile(160, 4, 37, 0, {"piece": 1, "lb": 3, "cup": 1.5, "package": 4})),
    (("flour", "bisquick", "baking mix"), NutritionProfile(110, 3, 23, 0, {"cup": 4, "tbsp": 0.25, "oz": 0.25, "package": 8})),
    (("sugar", "brown sugar", "powdered sugar", "confectioners sugar"), NutritionProfile(48, 0, 12, 0, {"tbsp": 1, "tsp": 0.33, "cup": 16, "oz": 0.25})),
    (("olive oil", "vegetable oil", "canola oil", "oil"), NutritionProfile(120, 0, 0, 14, {"tbsp": 1, "tsp": 0.33, "cup": 16})),
    (("butter", "margarine"), NutritionProfile(102, 0, 0, 12, {"tbsp": 1, "tsp": 0.33, "cup": 16, "stick": 8})),
    (("peanut butter", "almond butter"), NutritionProfile(190, 8, 7, 16, {"tbsp": 0.5, "cup": 8, "jar": 8})),
    (("walnut", "pecan", "almond", "peanut", "cashew", "nut"), NutritionProfile(170, 6, 6, 15, {"oz": 1, "cup": 5, "tbsp": 0.35, "package": 5})),
    (("milk", "evaporated milk", "condensed milk"), NutritionProfile(100, 8, 12, 3, {"cup": 1, "tbsp": 0.0625, "tsp": 0.02, "can": 1.5})),
    (("greek yogurt",), NutritionProfile(130, 17, 6, 3, {"cup": 1.33, "tbsp": 0.083, "package": 1})),
    (("yogurt", "yoghurt"), NutritionProfile(120, 8, 16, 3, {"cup": 1, "tbsp": 0.0625, "package": 1})),
    (("cream cheese",), NutritionProfile(100, 2, 2, 10, {"oz": 1, "tbsp": 0.5, "package": 8})),
    (("sour cream",), NutritionProfile(60, 1, 2, 5, {"tbsp": 0.5, "cup": 8, "package": 8})),
    (("heavy cream", "whipping cream", "cream"), NutritionProfile(100, 1, 1, 11, {"tbsp": 0.5, "cup": 8, "package": 8})),
    (("parmesan", "mozzarella", "cheddar", "ricotta", "feta", "swiss", "monterey jack", "cheese"), NutritionProfile(110, 7, 1, 9, {"oz": 1, "cup": 4, "tbsp": 0.25, "slice": 1, "package": 8, "lb": 16})),
    (("mayonnaise", "mayo"), NutritionProfile(90, 0, 0, 10, {"tbsp": 1, "cup": 16, "jar": 8})),
    (("avocado",), NutritionProfile(240, 3, 12, 22, {"piece": 1, "cup": 1.5})),
    (("tomato sauce", "marinara", "salsa"), NutritionProfile(40, 1, 8, 0, {"cup": 1, "tbsp": 0.06, "jar": 2, "can": 1.5})),
    (("cream of mushroom soup", "cream of chicken soup", "cream soup"), NutritionProfile(140, 3, 14, 8, {"can": 1, "cup": 1})),
    (("broth", "stock"), NutritionProfile(15, 1, 1, 0, {"cup": 1, "can": 1.5, "package": 4})),
    (("corn", "peas", "carrot", "broccoli", "spinach", "tomato", "pepper", "onion", "cabbage", "zucchini", "squash", "mushroom", "green bean", "vegetable"), NutritionProfile(30, 1, 6, 0, {"cup": 1, "piece": 1, "can": 2, "package": 4})),
    (("banana", "apple", "berry", "blueberry", "strawberry", "peach", "pineapple", "orange", "fruit"), NutritionProfile(60, 1, 15, 0, {"cup": 1, "piece": 1, "can": 2, "package": 4})),
    (("cereal", "granola"), NutritionProfile(200, 4, 40, 4, {"cup": 1, "package": 6})),
)


def load_seed_corpus(seed_path: Path) -> List[Dict[str, Any]]:
    if not seed_path.exists():
        return []
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    normalized: List[Dict[str, Any]] = []
    for item in payload:
        recipe = RecipeRecord.model_validate(item).model_dump(mode="json")
        recipe["cuisine"] = normalize_cuisine_name(recipe["cuisine"])
        normalized.append(recipe)
    return normalized


def build_recipe_corpus(
    source_path: Path,
    output_path: Path,
    target_count: int = 2000,
    curated_seed_path: Optional[Path] = None,
    target_meal_counts: Optional[Mapping[str, int]] = None,
    progress_every: int = PROGRESS_EVERY,
) -> BuildSummary:
    curated_seed_path = curated_seed_path or output_path
    target_meal_counts = dict(target_meal_counts or DEFAULT_TARGET_MEAL_COUNTS)
    curated_records = load_seed_corpus(curated_seed_path)

    processed_rows = 0
    eligible_rows = 0
    skipped_rows = 0
    bucket_store: Dict[Tuple[str, str], Dict[str, CorpusCandidate]] = defaultdict(dict)

    with source_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for processed_rows, row in enumerate(reader, start=1):
            candidate = normalize_recipe_nlg_row(row)
            if candidate is None:
                skipped_rows += 1
            else:
                eligible_rows += 1
                bucket_key = (candidate.primary_meal_type, candidate.cuisine)
                bucket = bucket_store[bucket_key]
                previous = bucket.get(candidate.dedupe_key)
                if previous is None or _candidate_sort_key(candidate) > _candidate_sort_key(previous):
                    bucket[candidate.dedupe_key] = candidate
                if len(bucket) > PRUNE_BUCKET_AT:
                    bucket_store[bucket_key] = _prune_bucket(bucket, MAX_BUCKET_SIZE)

            if progress_every and processed_rows % progress_every == 0:
                print(
                    "Processed {rows} rows; eligible={eligible}, skipped={skipped}, buckets={bucket_count}".format(
                        rows=processed_rows,
                        eligible=eligible_rows,
                        skipped=skipped_rows,
                        bucket_count=len(bucket_store),
                    )
                )

    for bucket_key, bucket in list(bucket_store.items()):
        bucket_store[bucket_key] = _prune_bucket(bucket, MAX_BUCKET_SIZE)

    selected = _select_balanced_candidates(
        curated_records=curated_records,
        bucket_store=bucket_store,
        target_count=target_count,
        target_meal_counts=target_meal_counts,
    )

    payload = [RecipeRecord.model_validate(recipe).model_dump(mode="json") for recipe in selected]
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    meal_type_counts = Counter(_primary_meal_type(item["meal_types"]) for item in payload)
    cuisine_counts = Counter(item["cuisine"] for item in payload)
    tag_counts = Counter(tag for item in payload for tag in item["tags"])
    return BuildSummary(
        target_count=target_count,
        selected_count=len(payload),
        processed_rows=processed_rows,
        eligible_rows=eligible_rows,
        skipped_rows=skipped_rows,
        output_path=str(output_path),
        source_path=str(source_path),
        meal_type_counts=dict(sorted(meal_type_counts.items())),
        cuisine_counts=dict(cuisine_counts.most_common(12)),
        tag_counts=dict(tag_counts.most_common(12)),
    )


def normalize_recipe_nlg_row(row: Mapping[str, str]) -> Optional[CorpusCandidate]:
    if row.get("source") and row.get("source") != "Gathered":
        return None

    title = clean_text(row.get("title", ""))
    if len(title) < 4:
        return None

    lower_title = normalize_for_matching(title)
    if _contains_any(lower_title, BEVERAGE_KEYWORDS):
        return None
    if _contains_any(lower_title, CONDIMENT_KEYWORDS) and not _contains_any(
        lower_title, APPETIZER_KEYWORDS + PROTEIN_HINTS + DINNER_KEYWORDS + LUNCH_KEYWORDS
    ):
        return None
    if _contains_any(lower_title, STRONG_DESSERT_KEYWORDS) and not _contains_any(lower_title, BREAKFAST_KEYWORDS):
        return None

    ingredient_lines = _safe_json_list(row.get("ingredients", "[]"))
    directions = [clean_text(item) for item in _safe_json_list(row.get("directions", "[]")) if clean_text(item)]
    ner_names = [clean_text(item) for item in _safe_json_list(row.get("NER", "[]")) if clean_text(item)]

    if not 3 <= len(ingredient_lines) <= 20:
        return None
    if len(directions) < 2:
        return None
    if len(" ".join(directions)) < 70:
        return None

    ingredients = build_ingredients(ingredient_lines, ner_names)
    ingredient_names = [item["name"] for item in ingredients]
    ingredient_text = " ".join(ingredient_names)
    directions_text = " ".join(directions)
    full_text = " ".join((title, ingredient_text, directions_text))
    normalized_text = normalize_for_matching(full_text)
    if _contains_any(normalized_text, ("gelatin", "jello", "pie filling", "frozen dessert")) and not _contains_any(
        normalized_text, BREAKFAST_KEYWORDS
    ):
        return None
    if _contains_any(lower_title, WEAK_DESSERT_TITLE_KEYWORDS) and not _contains_any(
        normalized_text, PROTEIN_HINTS + LUNCH_KEYWORDS + DINNER_KEYWORDS
    ):
        return None

    meal_types = infer_meal_types(title, normalized_text, ingredient_names)
    if not meal_types:
        return None
    primary_meal = meal_types[0]

    cuisine = infer_cuisine(title, normalized_text)
    prep_time_min = estimate_prep_time(ingredient_lines, directions, normalized_text, primary_meal)
    servings = estimate_servings(title, directions, primary_meal, len(ingredient_lines))
    calories, protein_g, carbs_g, fat_g = estimate_macros(ingredients, primary_meal, servings)
    tags = infer_tags(ingredient_names, meal_types, title, normalized_text, prep_time_min, protein_g)

    link = clean_text(row.get("link", ""))
    source_url = None
    if link:
        source_url = link if link.startswith(("http://", "https://")) else "https://{link}".format(link=link.lstrip("/"))

    row_id = clean_text(row.get("", "")) or clean_text(row.get("id", ""))
    recipe_id = "recipenlg-{slug}-{row_id}".format(
        slug=slugify(title)[:48],
        row_id=row_id or hashlib.sha1(title.encode("utf-8")).hexdigest()[:8],
    )
    payload = {
        "recipe_id": recipe_id,
        "name": title,
        "cuisine": cuisine,
        "meal_types": meal_types,
        "ingredients": ingredients,
        "prep_time_min": prep_time_min,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "tags": tags,
        "instructions": directions,
        "source_url": source_url,
    }
    dedupe_key = build_dedupe_key(title, ingredient_names)
    quality_score = score_candidate(payload)
    return CorpusCandidate(
        dedupe_key=dedupe_key,
        primary_meal_type=primary_meal,
        cuisine=cuisine,
        quality_score=quality_score,
        tiebreak=stable_hash(dedupe_key),
        payload=payload,
    )


def build_ingredients(ingredient_lines: Sequence[str], ner_names: Sequence[str]) -> List[Dict[str, Any]]:
    ingredients: List[Dict[str, Any]] = []
    for index, raw_line in enumerate(ingredient_lines):
        raw_line = clean_text(raw_line)
        entity_name = ner_names[index] if index < len(ner_names) else ""
        quantity, unit, remainder = parse_quantity_and_unit(raw_line)
        name = clean_ingredient_name(entity_name or remainder or raw_line)
        note = ""
        if raw_line and normalize_for_matching(raw_line) != normalize_for_matching(name):
            note = raw_line
        ingredients.append(
            {
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "note": note,
            }
        )
    return ingredients


def infer_meal_types(title: str, normalized_text: str, ingredient_names: Sequence[str]) -> List[str]:
    meal_types: List[str] = []
    lower_title = normalize_for_matching(title)
    ingredient_text = normalize_for_matching(" ".join(ingredient_names))

    breakfast_title_keywords = (
        "breakfast",
        "brunch",
        "oatmeal",
        "overnight oat",
        "granola",
        "pancake",
        "waffle",
        "omelet",
        "omelette",
        "frittata",
        "scramble",
        "smoothie",
        "parfait",
        "bagel",
        "muffin",
        "scone",
        "cereal",
        "banana bread",
        "pumpkin bread",
        "zucchini bread",
    )
    toast_breakfast = "toast" in lower_title and not _contains_any(normalized_text, MEAT_KEYWORDS)
    breakfast_hit = _contains_any(lower_title, breakfast_title_keywords) or (
        _contains_any(ingredient_text, ("oats", "granola"))
        and not _contains_any(lower_title, DINNER_KEYWORDS + LUNCH_KEYWORDS)
    ) or toast_breakfast
    lunch_hit = _contains_any(lower_title, LUNCH_KEYWORDS) or _contains_any(
        lower_title, ("salad", "sandwich", "wrap", "burger", "slaw")
    )
    dinner_hit = _contains_any(lower_title, DINNER_KEYWORDS) or (
        _contains_any(normalized_text, PROTEIN_HINTS) and not lunch_hit
    )
    snack_hit = _contains_any(lower_title, SNACK_KEYWORDS) or _contains_any(lower_title, APPETIZER_KEYWORDS)

    if breakfast_hit:
        meal_types.append("breakfast")
        if _contains_any(lower_title, ("smoothie", "parfait", "chia pudding", "bar", "energy bite")):
            meal_types.append("snack")
    if lunch_hit:
        meal_types.append("lunch")
    if dinner_hit:
        meal_types.append("dinner")
        if _contains_any(lower_title, ("soup", "chili", "salad", "bowl")):
            meal_types.append("lunch")
    if snack_hit and "snack" not in meal_types:
        meal_types.append("snack")

    if not meal_types:
        if _contains_any(lower_title, breakfast_title_keywords) or _contains_any(
            ingredient_text, ("oats", "granola")
        ):
            meal_types.append("breakfast")
        elif _contains_any(normalized_text, ("salad", "soup", "wrap", "sandwich")):
            meal_types.extend(["lunch", "dinner"] if "soup" in normalized_text else ["lunch"])
        else:
            meal_types.append("dinner")

    deduped: List[str] = []
    for meal_type in meal_types:
        if meal_type in MEAL_TYPES and meal_type not in deduped:
            deduped.append(meal_type)
    return deduped


def infer_cuisine(title: str, normalized_text: str) -> str:
    title_text = normalize_for_matching(title)
    cuisine_keywords: Mapping[str, Sequence[str]] = {
        "mexican": ("taco", "enchilada", "quesadilla", "salsa", "cilantro", "jalapeno", "fajita", "tortilla"),
        "italian": ("parmesan", "mozzarella", "ricotta", "lasagna", "marinara", "alfredo", "meatball", "spaghetti", "pasta", "oregano"),
        "thai": ("thai", "coconut milk", "red curry", "green curry", "fish sauce", "lemongrass", "peanut sauce"),
        "indian": ("curry", "garam masala", "turmeric", "paneer", "naan", "dal", "tikka"),
        "chinese": ("soy sauce", "bok choy", "hoisin", "stir fry", "stir-fry", "fried rice", "lo mein"),
        "japanese": ("teriyaki", "miso", "sushi", "udon", "soba", "panko"),
        "mediterranean": ("feta", "olive", "cucumber", "tzatziki", "oregano", "lemon", "hummus", "gyro"),
        "middle eastern": ("tahini", "falafel", "shawarma", "zaatar", "za'atar"),
        "southern": ("cornbread", "grits", "cajun", "gumbo", "jambalaya", "black eyed pea", "collard"),
        "french": ("quiche", "gratin", "dijon", "bechamel", "provencal"),
    }
    scored: Dict[str, int] = {}
    for cuisine, keywords in cuisine_keywords.items():
        score = sum(2 if keyword in title_text else 1 for keyword in keywords if keyword in normalized_text)
        if score:
            scored[cuisine] = score
    if not scored:
        return "american"
    return normalize_cuisine_name(max(sorted(scored), key=lambda item: scored[item]))


def estimate_prep_time(
    ingredient_lines: Sequence[str],
    directions: Sequence[str],
    normalized_text: str,
    primary_meal_type: str,
) -> int:
    ingredient_count = len(ingredient_lines)
    step_count = len(directions)
    if primary_meal_type == "breakfast":
        base = 1.0 + (ingredient_count * 0.45) + (step_count * 0.55)
    elif primary_meal_type == "lunch":
        base = 1.5 + (ingredient_count * 0.60) + (step_count * 0.75)
    elif primary_meal_type == "snack":
        base = 1.0 + (ingredient_count * 0.40) + (step_count * 0.45)
    else:
        base = 3.0 + (ingredient_count * 0.85) + (step_count * 1.0)

    if "slow cooker" in normalized_text or "crock pot" in normalized_text or "crockpot" in normalized_text:
        base += 4
    if "sheet pan" in normalized_text:
        base += 2
    if "no bake" in normalized_text or "no-bake" in normalized_text:
        base -= 2
    if not _contains_any(normalized_text, COOKING_VERBS):
        base -= 2

    explicit_minutes = min(5, sum(_extract_active_minutes(sentence) for sentence in directions))
    estimated = base + explicit_minutes
    max_by_meal = {"breakfast": 15, "lunch": 20, "dinner": 35, "snack": 10}
    return max(3, min(max_by_meal[primary_meal_type], int(round(estimated))))


def estimate_servings(title: str, directions: Sequence[str], primary_meal_type: str, ingredient_count: int) -> int:
    combined = " ".join((title, *directions))
    normalized = normalize_for_matching(combined)
    patterns = (
        r"\bserves\s+(\d{1,2})\b",
        r"\bserve\s+(\d{1,2})\b",
        r"\byields?\s+(\d{1,2})\b",
        r"\bmakes?\s+(\d{1,2})\s+servings?\b",
        r"\b(\d{1,2})\s+servings?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return max(1, min(12, int(match.group(1))))

    if primary_meal_type == "snack":
        if _contains_any(normalized, ("dip", "salsa", "hummus", "trail mix", "popcorn")):
            return 6
        return 4
    if primary_meal_type == "breakfast":
        if _contains_any(normalized, ("pancake", "waffle", "muffin", "scone", "biscuit")):
            return 6
        return 2 if ingredient_count <= 5 else 4
    if _contains_any(normalized, ("soup", "stew", "casserole", "chili", "pasta bake", "lasagna", "salad")):
        return 6
    return 4


def estimate_macros(
    ingredients: Sequence[Mapping[str, Any]],
    primary_meal_type: str,
    servings: int,
) -> Tuple[int, int, int, int]:
    total_calories = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    for ingredient in ingredients:
        calories, protein, carbs, fat = estimate_ingredient_macros(
            ingredient.get("name", ""),
            ingredient.get("quantity"),
            ingredient.get("unit"),
        )
        total_calories += calories
        total_protein += protein
        total_carbs += carbs
        total_fat += fat

    total_calories = max(total_calories, len(ingredients) * 32)
    calories = total_calories / max(servings, 1)
    protein = total_protein / max(servings, 1)
    carbs = total_carbs / max(servings, 1)
    fat = total_fat / max(servings, 1)

    max_calories = MAX_CALORIES_BY_MEAL[primary_meal_type]
    if calories > max_calories:
        scale_down = max_calories / calories
        calories *= scale_down
        protein *= scale_down
        carbs *= scale_down
        fat *= scale_down

    min_calories = MIN_CALORIES_BY_MEAL[primary_meal_type]
    macro_calories = max(1.0, (protein * 4) + (carbs * 4) + (fat * 9))
    if calories < min_calories:
        scale_up = min_calories / max(calories, 1.0)
        calories *= scale_up
        protein *= scale_up
        carbs *= scale_up
        fat *= scale_up
        macro_calories *= scale_up

    if abs(macro_calories - calories) > 30:
        scale = calories / max(macro_calories, 1.0)
        protein *= scale
        carbs *= scale
        fat *= scale
        macro_calories = (protein * 4) + (carbs * 4) + (fat * 9)
        calories = macro_calories

    final_max_calories = MAX_CALORIES_BY_MEAL[primary_meal_type]
    if calories > final_max_calories:
        scale = final_max_calories / calories
        calories *= scale
        protein *= scale
        carbs *= scale
        fat *= scale

    return (
        int(round(calories)),
        max(3, int(round(protein))),
        max(4, int(round(carbs))),
        max(2, int(round(fat))),
    )


def estimate_ingredient_macros(name: str, quantity: Any, unit: Any) -> Tuple[float, float, float, float]:
    normalized_name = normalize_for_matching(name)
    normalized_unit = normalize_unit(unit)
    amount = float(quantity) if isinstance(quantity, (int, float)) else 1.0
    amount = amount or 1.0

    for keywords, profile in NUTRITION_PROFILES:
        if any(keyword in normalized_name for keyword in keywords):
            multiplier = _profile_multiplier(profile, normalized_unit, amount)
            return (
                profile.calories * multiplier,
                profile.protein * multiplier,
                profile.carbs * multiplier,
                profile.fat * multiplier,
            )

    generic_multiplier = amount
    if normalized_unit == "cup":
        generic_multiplier *= 1.5
    elif normalized_unit == "tbsp":
        generic_multiplier *= 0.25
    elif normalized_unit == "tsp":
        generic_multiplier *= 0.08
    elif normalized_unit == "lb":
        generic_multiplier *= 3
    elif normalized_unit == "oz":
        generic_multiplier *= 0.5
    return (30 * generic_multiplier, 1 * generic_multiplier, 4 * generic_multiplier, 1 * generic_multiplier)


def infer_tags(
    ingredient_names: Sequence[str],
    meal_types: Sequence[str],
    title: str,
    normalized_text: str,
    prep_time_min: int,
    protein_g: int,
) -> List[str]:
    tags: List[str] = []

    contains_meat = _contains_any(normalized_text, MEAT_KEYWORDS)
    contains_dairy = _contains_any(normalized_text, DAIRY_KEYWORDS)
    contains_egg = _contains_any(normalized_text, EGG_KEYWORDS)
    contains_gluten = _contains_any(normalized_text, GLUTEN_KEYWORDS)
    contains_honey_or_gelatin = _contains_any(normalized_text, HONEY_GELATIN_KEYWORDS)

    if not contains_meat:
        tags.append("vegetarian")
    if not contains_meat and not contains_dairy and not contains_egg and not contains_honey_or_gelatin:
        tags.append("vegan")
    if not contains_dairy:
        tags.append("dairy-free")
    if not contains_gluten:
        tags.append("gluten-free")
    if prep_time_min <= 20:
        tags.append("quick")
    if protein_g >= PROTEIN_TAG_THRESHOLD:
        tags.append("high-protein")
    if "snack" in meal_types and not _contains_any(normalized_text, COOKING_VERBS):
        tags.append("no-cook")
    if _contains_any(normalized_text, ("overnight", "refrigerate", "chill", "marinate ahead")):
        tags.append("make-ahead")
    if _contains_any(normalize_for_matching(title), APPETIZER_KEYWORDS):
        tags.append("appetizer")

    deduped: List[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


def score_candidate(payload: Mapping[str, Any]) -> float:
    ingredients = payload["ingredients"]
    instructions = payload["instructions"]
    tags = set(payload["tags"])
    score = 40.0
    score += min(len(ingredients), 10) * 2.0
    score += min(len(instructions), 8) * 1.5
    score += 4.0 if payload["cuisine"] != "american" else 0.0
    score += 4.0 if "high-protein" in tags else 0.0
    score += 3.0 if "quick" in tags else 0.0
    score += 2.0 if len(payload["meal_types"]) > 1 else 0.0
    score += 2.0 if payload["prep_time_min"] <= 30 else 0.0
    score += 2.0 if 220 <= payload["calories"] <= 780 else 0.0
    return score


def parse_quantity_and_unit(raw_line: str) -> Tuple[Optional[float], Optional[str], str]:
    if not raw_line:
        return None, None, ""
    normalized = raw_line
    for raw_fraction, replacement in RAW_UNICODE_FRACTIONS.items():
        normalized = normalized.replace(raw_fraction, replacement)
    normalized = normalized.strip()

    quantity: Optional[float] = None
    remaining = normalized
    match = re.match(r"^\s*(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)", normalized)
    if match:
        quantity = parse_fraction(match.group(1))
        remaining = normalized[match.end() :].strip()

    if remaining.startswith("("):
        depth = 0
        index = 0
        while index < len(remaining):
            char = remaining[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    index += 1
                    break
            index += 1
        remaining = remaining[index:].strip(",; ")

    parts = remaining.split(maxsplit=1)
    unit = None
    if parts:
        maybe_unit = re.sub(r"[^a-zA-Z]", "", parts[0]).lower()
        unit = normalize_unit(maybe_unit)
        if unit:
            remaining = parts[1].strip() if len(parts) > 1 else ""
        else:
            unit = None

    return quantity, unit, remaining


def parse_fraction(value: str) -> Optional[float]:
    cleaned = value.strip().replace("-", " ")
    if not cleaned:
        return None
    total = 0.0
    for part in cleaned.split():
        if "/" in part:
            numerator, denominator = part.split("/", 1)
            try:
                total += float(numerator) / float(denominator)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        else:
            try:
                total += float(part)
            except (TypeError, ValueError):
                return None
    return total or None


def clean_ingredient_name(value: str) -> str:
    cleaned = clean_text(value)
    cleaned = re.sub(r"^[,;:.-]+", "", cleaned).strip()
    if not cleaned:
        return "ingredient"
    return cleaned.lower()


def normalize_unit(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"[^a-zA-Z]", "", str(value)).lower()
    if not cleaned:
        return None
    return UNIT_ALIASES.get(cleaned)


def normalize_cuisine_name(value: str) -> str:
    cleaned = normalize_for_matching(value)
    aliases = {
        "middle-eastern": "middle eastern",
        "middle eastern": "middle eastern",
    }
    return aliases.get(cleaned, cleaned or "american")


def build_dedupe_key(title: str, ingredient_names: Sequence[str]) -> str:
    normalized_ingredients = sorted(slugify(name) for name in ingredient_names if name)[:4]
    return "{title}|{ingredients}".format(title=slugify(title), ingredients=";".join(normalized_ingredients))


def slugify(value: str) -> str:
    normalized = normalize_for_matching(value)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-") or "recipe"


def clean_text(value: str) -> str:
    if value is None:
        return ""
    cleaned = str(value).replace("\\u00b0", " degrees ")
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.replace("'S", "'s")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_for_matching(value: str) -> str:
    cleaned = clean_text(value).lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9\s-]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _safe_json_list(raw_value: str) -> List[str]:
    try:
        loaded = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    haystack = " {text} ".format(text=text.replace("-", " "))
    for keyword in keywords:
        needle = " {keyword} ".format(keyword=str(keyword).replace("-", " ").strip())
        if needle in haystack:
            return True
    return False


def _extract_active_minutes(sentence: str) -> int:
    normalized = normalize_for_matching(sentence)
    total = 0.0
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(minute|minutes|min|hour|hours|hr|hrs)\b", normalized):
        value = float(match.group(1))
        unit = match.group(2)
        minutes = value * 60 if unit.startswith("hour") or unit.startswith("hr") else value
        window = normalized[max(match.start() - 20, 0) : min(match.end() + 20, len(normalized))]
        if _contains_any(window, PASSIVE_TIME_VERBS):
            total += min(2, minutes * 0.02)
        else:
            total += min(4, minutes * 0.06)
    if "overnight" in normalized:
        total += 1
    return int(round(total))


def _profile_multiplier(profile: NutritionProfile, unit: Optional[str], amount: float) -> float:
    if unit and unit in profile.unit_multipliers:
        return profile.unit_multipliers[unit] * amount
    if unit == "tbsp":
        return amount * 0.25
    if unit == "tsp":
        return amount * 0.08
    if unit == "cup":
        return amount * 1.5
    if unit == "lb":
        return amount * 4
    if unit == "oz":
        return amount * 0.5
    return amount


def _candidate_sort_key(candidate: CorpusCandidate) -> Tuple[float, str]:
    return (candidate.quality_score, candidate.tiebreak)


def _prune_bucket(bucket: Mapping[str, CorpusCandidate], limit: int) -> Dict[str, CorpusCandidate]:
    sorted_candidates = sorted(bucket.values(), key=_candidate_sort_key, reverse=True)[:limit]
    return {candidate.dedupe_key: candidate for candidate in sorted_candidates}


def _select_balanced_candidates(
    curated_records: Sequence[Mapping[str, Any]],
    bucket_store: Mapping[Tuple[str, str], Mapping[str, CorpusCandidate]],
    target_count: int,
    target_meal_counts: Mapping[str, int],
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = [dict(recipe) for recipe in curated_records]
    selected_keys = {build_dedupe_key(recipe["name"], [item["name"] for item in recipe["ingredients"]]) for recipe in selected}
    meal_counts = Counter(_primary_meal_type(recipe["meal_types"]) for recipe in selected)
    bucket_selected_counts: Counter[Tuple[str, str]] = Counter()
    cuisine_selected_counts: Counter[str] = Counter(recipe["cuisine"] for recipe in selected)

    bucket_lists: Dict[Tuple[str, str], List[CorpusCandidate]] = {
        bucket_key: sorted(bucket.values(), key=_candidate_sort_key, reverse=True)
        for bucket_key, bucket in bucket_store.items()
    }
    bucket_indices = defaultdict(int)

    desired_by_meal = {meal_type: max(0, target_meal_counts.get(meal_type, 0) - meal_counts.get(meal_type, 0)) for meal_type in MEAL_TYPES}

    while len(selected) < target_count:
        progress = False
        for meal_type in MEAL_TYPES:
            if len(selected) >= target_count:
                break
            if desired_by_meal[meal_type] <= 0:
                continue
            bucket_key = _choose_bucket_for_meal(
                meal_type=meal_type,
                bucket_lists=bucket_lists,
                bucket_indices=bucket_indices,
                bucket_selected_counts=bucket_selected_counts,
                cuisine_selected_counts=cuisine_selected_counts,
            )
            if bucket_key is None:
                continue
            payload = _take_next_candidate(bucket_key, bucket_lists, bucket_indices, selected_keys)
            if payload is None:
                continue
            selected.append(payload)
            selected_keys.add(build_dedupe_key(payload["name"], [item["name"] for item in payload["ingredients"]]))
            desired_by_meal[meal_type] -= 1
            meal_counts[meal_type] += 1
            bucket_selected_counts[bucket_key] += 1
            cuisine_selected_counts[payload["cuisine"]] += 1
            progress = True
        if not progress:
            break

    while len(selected) < target_count:
        bucket_key = _choose_bucket_for_meal(
            meal_type=None,
            bucket_lists=bucket_lists,
            bucket_indices=bucket_indices,
            bucket_selected_counts=bucket_selected_counts,
            cuisine_selected_counts=cuisine_selected_counts,
        )
        if bucket_key is None:
            break
        payload = _take_next_candidate(bucket_key, bucket_lists, bucket_indices, selected_keys)
        if payload is None:
            continue
        selected.append(payload)
        selected_keys.add(build_dedupe_key(payload["name"], [item["name"] for item in payload["ingredients"]]))
        bucket_selected_counts[bucket_key] += 1
        cuisine_selected_counts[payload["cuisine"]] += 1

    return selected[:target_count]


def _choose_bucket_for_meal(
    meal_type: Optional[str],
    bucket_lists: Mapping[Tuple[str, str], Sequence[CorpusCandidate]],
    bucket_indices: Mapping[Tuple[str, str], int],
    bucket_selected_counts: Mapping[Tuple[str, str], int],
    cuisine_selected_counts: Mapping[str, int],
) -> Optional[Tuple[str, str]]:
    candidates: List[Tuple[Tuple[int, int, int, str], Tuple[str, str]]] = []
    for bucket_key, candidate_list in bucket_lists.items():
        bucket_meal, cuisine = bucket_key
        if meal_type and bucket_meal != meal_type:
            continue
        if bucket_indices[bucket_key] >= len(candidate_list):
            continue
        selected_count = bucket_selected_counts.get(bucket_key, 0)
        cuisine_count = cuisine_selected_counts.get(cuisine, 0)
        remaining = len(candidate_list) - bucket_indices[bucket_key]
        candidates.append(((selected_count, cuisine_count, -remaining, cuisine), bucket_key))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _take_next_candidate(
    bucket_key: Tuple[str, str],
    bucket_lists: Mapping[Tuple[str, str], Sequence[CorpusCandidate]],
    bucket_indices: defaultdict[Tuple[str, str], int],
    selected_keys: set[str],
) -> Optional[Dict[str, Any]]:
    candidate_list = bucket_lists[bucket_key]
    index = bucket_indices[bucket_key]
    while index < len(candidate_list):
        candidate = candidate_list[index]
        index += 1
        bucket_indices[bucket_key] = index
        if candidate.dedupe_key in selected_keys:
            continue
        return candidate.payload
    bucket_indices[bucket_key] = index
    return None


def _primary_meal_type(meal_types: Sequence[str]) -> str:
    for meal_type in MEAL_TYPES:
        if meal_type in meal_types:
            return meal_type
    return "dinner"
