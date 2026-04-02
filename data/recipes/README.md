Phase 2 stores a normalized sample recipe corpus here.

`phase2_recipe_corpus.json` is shaped to match the planned retrieval contract:

- `recipe_id`, `name`, `cuisine`
- `meal_types`, `ingredients`, `prep_time_min`
- `calories`, `protein_g`, `carbs_g`, `fat_g`
- `tags`, `instructions`, `source_url`

The app now supports a real Qdrant-backed retrieval path for production and keeps the
local hybrid scorer as a fallback when `SHOPPER_QDRANT_URL` is unset.

The corpus is now built from `full_dataset.csv` with:

- `data/recipes/curated_recipe_seed.json` as the preserved hand-authored seed set
- `scripts/build_recipe_corpus.py` as the deterministic builder entrypoint

The builder streams RecipeNLG, filters out clearly low-signal dessert/condiment rows,
normalizes records into the app schema, infers meal types/cuisine/tags, estimates
per-serving nutrition, and writes a 2,000-recipe corpus back to
`phase2_recipe_corpus.json`.
