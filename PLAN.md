# AI Meal Planner + Grocery Shopping Agent — Final Implementation Plan

## Context

Build a production-quality multi-agent system that plans meals, optimizes grocery shopping, and executes purchases. This is a portfolio project designed to demonstrate every technical competency in the target job description. The architecture prioritizes **selective agentization** — LLM agents where judgment is needed, deterministic code where it isn't — with strong evaluation, observability, and governance from the start.

### Design Principles

1. **Selective agentization**: Not everything is an agent. TDEE math is code. Ingredient aggregation is code. Meal selection with tradeoffs is an agent. Repair happens through critic feedback and bounded replanning, not a standalone substitution agent.
2. **Evals from day 1**: Every phase ships with its evaluators. The eval harness is not a late-stage add-on.
3. **Bounded autonomy**: LLM-powered browser agent for flexible navigation, deterministic verification gates for correctness, human approval before irreversible actions.
4. **Run-centric, not CRUD-centric**: The API models graph execution runs, not individual resources.
5. **Custom orchestration**: Hand-built supervisor and subgraphs, not `langgraph-supervisor` abstractions.
6. **Memory as a first-class subsystem**: Four distinct memory layers (short-term run state, long-term canonical facts, episodic memories, procedural prompts/policies) with explicit context assembly per node — no raw state dumps into prompts.
7. **Frontend as the trust layer**: The UI makes agent behavior transparent — live progress streaming, verification results before approval, learned preferences the user can inspect and correct. Built alongside each backend phase, not bolted on later.

### Status Note

This plan includes phase-by-phase milestone notes. When those historical snapshots differ from the current repo, the **Current Architecture** section below is the source of truth for today's implementation.

### Current Architecture

- Top-level graph: `supervisor → load_memory → planning_subgraph → planning_critic_subgraph → shopping_subgraph → shopping_critic_subgraph → end`
- Planning worker path: `nutrition_planner` does deterministic macro-target calculation plus a narrow nutrition-plan validator; `meal_selector` does whole-week recipe selection and then runs deterministic slot-coverage and safety guards before returning.
- Planning boundary critic: `PlanningCriticNode` runs once after the planning subgraph, combines deterministic week-level checks (macro alignment, groundedness, variety heuristics) with optional LLM review, and on failure routes back through a bounded planning replan loop with structured `repair_instructions`.
- Shopping worker path: `grocery_builder` deterministically aggregates ingredients, diffs against fridge inventory, and validates the derived grocery list; `price_optimizer` fans out to store adapters, applies deterministic ranking and budget guards, and optionally uses an LLM only for final tradeoff selection.
- Shopping boundary critic: `ShoppingCriticNode` runs once after the shopping subgraph, checks final purchase-order coverage and budget fit, adds optional LLM review, and surfaces structured `repair_instructions` plus `replan_reason` on failure.
- There is no dedicated substitution node in the current repo. Cost or availability problems are represented as critic feedback and replan reasons inside the existing worker/critic orchestration.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph (`StateGraph`, custom supervisor) | JD requires LangGraph; custom gives deeper learning + better interview story |
| LLM (reasoning) | Claude Sonnet (primary), Claude Haiku (simple tasks) | Model routing for cost optimization |
| LangChain | Minimal — model wrappers (`langchain-anthropic`), `@tool` decorator, `langchain-qdrant` | Utility library only, not orchestration |
| Vector DB | Qdrant | Native hybrid search (dense + sparse), self-hostable, reranking support |
| Persistence | PostgreSQL | User profiles, orders, feedback, audit trail, LangGraph checkpoints |
| Checkpointing | `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`) | Durable pause/resume for human-in-the-loop |
| Long-term Memory | LangGraph Store (namespaced, semantic search) | Episodic memories across sessions; thin wrapper for portability |
| Backend | FastAPI + SSE | Run-centric API, real-time agent progress streaming |
| Browser Agent | browser-use (primary) + Playwright (verification/fallback) | LLM-controlled navigation + deterministic cart verification |
| Tracing/Eval | LangSmith | Tracing from day 1, eval datasets, experiments, online monitoring |
| Embeddings | OpenAI `text-embedding-3-small` | Recipe vectorization for Qdrant |
| Cache | Redis (Phase 7) | LLM response caching, quote caching for cost reduction |
| Recipe Data | RecipeNLG or Epicurious dataset (real, not LLM-generated) | Groundedness requires real source data |
| Frontend | Next.js 15 (App Router) + TypeScript | SSR, React Server Components, great DX, portfolio-friendly |
| UI Components | shadcn/ui + Tailwind CSS 4 | Beautiful defaults, accessible, copy-paste not dependency |
| State/Data Fetching | TanStack Query (React Query) | Cache, SSE integration, optimistic updates, devtools |
| Forms | React Hook Form + Zod | Validation mirrors backend Pydantic schemas |
| Charts | Recharts | Lightweight, composable, good for nutrition/budget viz |
| Real-time | Native EventSource (SSE) | Matches backend SSE streaming, no WebSocket overhead |

---

## Project Structure

```
shopper/
├── pyproject.toml
├── .env.example
├── docker-compose.yml                # Postgres + Qdrant (+ Redis in Phase 7)
├── alembic/                          # DB migrations
│   └── versions/
├── web/                              # Next.js frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── components.json               # shadcn/ui config
│   ├── public/
│   ├── src/
│   │   ├── app/                      # App Router pages
│   │   │   ├── layout.tsx            # Root layout — nav, providers
│   │   │   ├── page.tsx              # Landing / dashboard
│   │   │   ├── onboarding/
│   │   │   │   └── page.tsx          # New user profile creation
│   │   │   ├── profile/
│   │   │   │   └── page.tsx          # Edit profile + dietary prefs
│   │   │   ├── runs/
│   │   │   │   ├── page.tsx          # Run history list
│   │   │   │   ├── new/
│   │   │   │   │   └── page.tsx      # Start a new run
│   │   │   │   └── [runId]/
│   │   │   │       ├── page.tsx      # Live run progress + results
│   │   │   │       └── approve/
│   │   │   │           └── page.tsx  # Checkout approval gate (Phase 5)
│   │   │   ├── inventory/
│   │   │   │   └── page.tsx          # Fridge inventory CRUD (Phase 3)
│   │   │   └── feedback/
│   │   │       └── [runId]/
│   │   │           └── page.tsx      # Post-run feedback (Phase 6)
│   │   ├── components/               # Shared UI components
│   │   │   ├── ui/                   # shadcn/ui primitives (button, card, etc.)
│   │   │   ├── layout/
│   │   │   │   ├── nav.tsx           # Top nav / sidebar
│   │   │   │   └── providers.tsx     # QueryClientProvider, theme, etc.
│   │   │   ├── profile/
│   │   │   │   └── profile-form.tsx  # User profile form (reused in onboarding + edit)
│   │   │   ├── run/
│   │   │   │   ├── run-progress.tsx  # SSE-powered live progress tracker
│   │   │   │   ├── phase-stepper.tsx # Visual step indicator (planning→shopping→checkout)
│   │   │   │   └── run-card.tsx      # Run summary card for history list
│   │   │   ├── plan/
│   │   │   │   ├── meal-calendar.tsx # 7-day meal plan grid (Phase 2)
│   │   │   │   ├── recipe-card.tsx   # Individual recipe with macros (Phase 2)
│   │   │   │   └── nutrition-summary.tsx # Daily/weekly macro breakdown
│   │   │   ├── grocery/
│   │   │   │   ├── grocery-list.tsx  # Categorized grocery list (Phase 3)
│   │   │   │   └── price-table.tsx   # Store price comparison (Phase 4)
│   │   │   ├── checkout/
│   │   │   │   ├── cart-review.tsx   # Cart contents + screenshot (Phase 5)
│   │   │   │   └── approval-gate.tsx # Approve/reject/edit controls (Phase 5)
│   │   │   ├── inventory/
│   │   │   │   └── inventory-manager.tsx # Fridge item CRUD (Phase 3)
│   │   │   └── feedback/
│   │   │       ├── meal-rating.tsx   # Star rating + comment per meal (Phase 6)
│   │   │       └── preference-dashboard.tsx # Learned preferences viz (Phase 6)
│   │   ├── lib/
│   │   │   ├── api.ts                # Typed API client (wraps fetch, points to FastAPI)
│   │   │   ├── sse.ts                # SSE hook for run streaming
│   │   │   ├── types.ts              # TypeScript types mirroring backend Pydantic schemas
│   │   │   └── utils.ts              # cn() helper, formatters
│   │   └── hooks/
│   │       ├── use-run.ts            # TanStack Query hook for run state
│   │       ├── use-run-stream.ts     # SSE subscription hook
│   │       ├── use-user.ts           # User profile query/mutation hooks
│   │       └── use-inventory.ts      # Inventory CRUD hooks (Phase 3)
│   └── .env.local                    # NEXT_PUBLIC_API_URL=http://localhost:8000
├── data/
│   └── recipes/                      # Real recipe dataset (RecipeNLG extract)
├── src/shopper/
│   ├── __init__.py
│   ├── config.py                     # Settings via pydantic-settings
│   ├── main.py                       # FastAPI app
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── runs.py               # POST /runs, GET /runs/{id}, POST /runs/{id}/resume
│   │   │   ├── users.py              # User profile CRUD
│   │   │   ├── inventory.py          # Fridge inventory CRUD
│   │   │   ├── feedback.py           # Feedback submission
│   │   │   └── stream.py             # SSE streaming for run progress
│   │   └── deps.py                   # Dependency injection
│   ├── models/                       # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py                   # UserProfile
│   │   ├── recipe.py                 # Recipe (reference, not generated)
│   │   ├── run.py                    # PlanRun (execution record)
│   │   ├── inventory.py              # FridgeItem
│   │   ├── order.py                  # PurchaseOrder + OrderItem
│   │   ├── feedback.py               # UserFeedback
│   │   └── audit.py                  # AuditLog
│   ├── schemas/                      # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── run.py
│   │   ├── inventory.py
│   │   ├── feedback.py
│   │   └── common.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py                  # PlannerState + subgraph state types
│   │   ├── graph.py                  # build_planner_graph() — top-level assembly
│   │   ├── supervisor.py             # Custom supervisor routing (deterministic + LLM fallback)
│   │   ├── subgraphs/
│   │   │   ├── __init__.py
│   │   │   ├── planning.py           # Planning subgraph (nutrition + meal selection)
│   │   │   ├── shopping.py           # Shopping subgraph (grocery list + price optimization)
│   │   │   ├── critic.py             # Boundary critic subgraphs for planning + shopping
│   │   │   └── checkout.py           # Planned future phase
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── nutrition_planner.py  # Deterministic TDEE + LLM for edge cases
│   │   │   ├── meal_selector.py      # Whole-week LLM planner + deterministic output guards
│   │   │   ├── planning_critic.py    # Planning boundary critic
│   │   │   ├── grocery_builder.py    # Deterministic aggregation/diff + grocery validators
│   │   │   ├── price_optimizer.py    # Deterministic ranking + LLM tradeoff decisions
│   │   │   ├── shopping_critic.py    # Shopping boundary critic
│   │   │   ├── purchase_executor.py  # Planned future phase
│   │   │   └── feedback_processor.py # Planned future phase
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── nutrition_lookup.py   # USDA FoodData Central API
│   │       ├── recipe_search.py      # Qdrant retrieval tool
│   │       ├── store_scraper.py      # Store price fetching (1 real + mocks)
│   │       ├── inventory_tools.py    # Fridge CRUD tools
│   │       ├── browser_tools.py      # browser-use cart building + Playwright verification
│   │       └── cart_verifier.py      # Deterministic cart state verification
│   ├── memory/                        # Memory + context management subsystem
│   │   ├── __init__.py
│   │   ├── store.py                   # MemoryStore — thin wrapper over LangGraph Store
│   │   ├── context_assembler.py       # Per-node context building with token budgets
│   │   ├── distiller.py               # Background: feedback events → compact preference summary
│   │   └── types.py                   # EpisodicMemory, MemoryQuery, ContextBudget types
│   ├── services/                     # Deterministic business logic (NOT agents)
│   │   ├── __init__.py
│   │   ├── nutrition_calc.py         # TDEE, macro splits — pure math
│   │   ├── ingredient_aggregator.py  # Quantity aggregation, unit conversion, fridge diff
│   │   ├── price_ranker.py           # Price comparison, cheapest-per-item — pure sort
│   │   └── budget_checker.py         # Budget validation — pure math
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── qdrant_store.py           # QdrantRecipeStore (hybrid search + rerank)
│   │   ├── embeddings.py             # Embedding generation
│   │   ├── reranker.py               # Cross-encoder reranking
│   │   └── seed.py                   # Recipe DB seeding from real dataset
│   ├── prompts/
│   │   ├── meal_selector.md
│   │   ├── planning_critic.md
│   │   ├── shopping_critic.md
│   │   └── price_tradeoff.md         # Online vs in-store decision prompt
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── runner.py                 # Eval orchestrator
│   │   ├── datasets/                 # Golden test cases (built incrementally per phase)
│   │   │   ├── nutrition_cases.json
│   │   │   ├── meal_plan_cases.json
│   │   │   ├── safety_cases.json
│   │   │   ├── grocery_cases.json
│   │   │   ├── price_cases.json
│   │   │   └── browser_cases.json
│   │   ├── evaluators/
│   │   │   ├── nutrition_accuracy.py
│   │   │   ├── meal_relevance.py
│   │   │   ├── grocery_completeness.py
│   │   │   ├── price_optimality.py
│   │   │   ├── safety.py             # Allergen detection — zero tolerance
│   │   │   ├── groundedness.py       # Recipe hallucination detection
│   │   │   ├── browser_accuracy.py   # Cart accuracy, subtotal, fee verification
│   │   │   └── memory_quality.py     # Memory recall, staleness, relevance, no cross-user leakage
│   │   └── monitors/
│   │       └── online_monitor.py     # Production quality monitoring via LangSmith
│   └── validators/                   # Deterministic validation (not LLM)
│       ├── __init__.py
│       ├── nutrition_validator.py    # Macro bounds checking
│       ├── budget_validator.py       # Budget compliance
│       ├── safety_validator.py       # Allergen/restriction checking
│       └── cart_validator.py         # Cart state verification after browser actions
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/
└── scripts/
    ├── seed_recipes.py
    └── run_evals.py
```

---

## Architecture Overview

### LLM vs. Deterministic Code Split

| Component | Type | Why |
|---|---|---|
| TDEE / macro calculation | **Deterministic** service | Known formulas, no judgment needed |
| Meal selection + recipe matching | **LLM agent** | Balancing variety, preferences, schedule requires judgment |
| Ingredient extraction from recipes | **Deterministic** lookup | Recipes have structured ingredient lists |
| Quantity aggregation + fridge diff | **Deterministic** service | Math + set operations |
| Price comparison ranking | **Deterministic** service | Cheapest is cheapest — pure sort |
| Online vs. in-store split | **LLM-assisted decision** | Multi-factor tradeoff (fees, time value, preferences) |
| Critic-directed repair / replanning | **Structured routing** | Repairs reuse the existing worker subgraphs instead of a dedicated substitution node |
| Critic / verification | **Boundary deterministic checks** + optional LLM review | Worker nodes own narrow guards; critics review subgraph outputs once at the boundary |
| Browser cart building | **LLM agent** (browser-use) | Dynamic UI navigation |
| Cart state verification | **Deterministic** validator | SKU match, quantity, subtotal — must be exact |

### Subgraph Architecture

```
User Request
  -> supervisor
  -> load_memory
  -> planning_subgraph
       nutrition_planner
       meal_selector
  -> planning_critic_subgraph
       planning_critic
       on failure: structured repair_instructions -> planning_subgraph (bounded replan)
  -> shopping_subgraph
       grocery_builder
       price_optimizer
  -> shopping_critic_subgraph
       shopping_critic
       on failure: structured repair_instructions + replan_reason -> end failed
  -> end
```

- Worker nodes and subgraphs produce the artifacts for that phase.
- Deterministic validators do narrow checks inside the worker steps that own the data.
- Each phase has exactly one critic at the subgraph boundary.
- The current bounded repair loop exists on the planning boundary; shopping failures are surfaced through critic feedback and `replan_reason` without a standalone substitution hop.

Each subgraph has **private message history** — messages don't leak between subgraphs. Only structured state fields (nutrition_plan, selected_meals, grocery_list, etc.) pass between them via the top-level `PlannerState`.

### Memory & Context Management

#### Four Memory Layers

| Layer | Storage | What Lives Here | Lifetime |
|---|---|---|---|
| **Short-term (run)** | LangGraph checkpoints (`AsyncPostgresSaver`) | Current run state, subgraph scratch, interrupt payloads | Single run (persisted for resume/replay) |
| **Long-term canonical** | PostgreSQL (`UserProfile` + `UserPreferenceSummary`) | Stable facts: allergies, budget rules, household size, derived preference summary | Indefinite, updated via distillation |
| **Long-term episodic** | LangGraph Store (namespaced by `(user_id, category)`) | Feedback events, accepted/rejected replans, recurring dislikes, successful baskets | Indefinite, semantically searchable |
| **Procedural** | Version-controlled files in `prompts/` | Prompt templates, validation policies, store playbooks | Tied to code version (git) |

#### Why This Split (Not Everything in Qdrant)

- **Canonical facts** (allergies, household size) must be deterministically checked, not found via cosine similarity. "Allergic to peanuts" is a Postgres column checked by `safety_validator`, not an embedded text blob.
- **Episodic memories** ("loved the Thai basil chicken", "rejected the last budget-driven replan") benefit from semantic search — you want to retrieve *relevant* memories, not all memories. LangGraph Store supports namespaced semantic search natively.
- **Qdrant stays focused on recipe retrieval and recipe-level alternatives** — its core job. Don't overload it as a general memory store.
- **Procedural memory** is just versioned prompts and policies. No need for a memory system — git history + LangSmith experiments handle version comparison.

#### Memory Write Policy

Only write durable memories from **trusted signals**:
- Explicit user feedback (ratings, comments, "never again")
- Accepted/rejected replans or cheaper-plan alternatives
- Repeated cart edits (user keeps removing an item → signal)
- Completed purchase outcomes
- **Never** store raw chain-of-thought or model reasoning as memory

#### Memory Conflict Policy

- Newer explicit user statements override older inferred preferences
- Derived preference summaries are **recomputed from events** by the distiller, not hand-edited by the model
- Recent behavior outranks old behavior (recency weighting in retrieval)

#### MemoryStore (thin wrapper)

```python
# src/shopper/memory/store.py

class MemoryStore:
    """Thin wrapper over LangGraph Store for episodic memories.
    Abstracted so backend can be swapped if LangGraph Store API changes."""

    def __init__(self, store: BaseStore):
        self.store = store

    async def save_memory(
        self, user_id: str, category: str, content: str, metadata: dict
    ) -> str:
        """Write an episodic memory. Categories: 'meal_feedback', 'store_behavior',
        'substitution_decisions' (reserved for future/manual swap feedback),
        'general_preferences'."""
        namespace = (user_id, category)
        # store.put with semantic embedding for later retrieval
        ...

    async def recall(
        self, user_id: str, query: str, top_k: int = 5, categories: list[str] | None = None
    ) -> list[EpisodicMemory]:
        """Retrieve relevant memories via semantic search, scoped to user."""
        ...

    async def forget(self, user_id: str, memory_id: str) -> None:
        """Delete a specific memory (user requested or staleness cleanup)."""
        ...
```

#### ContextAssembler (per-node context building)

Each node gets a tailored context — not a raw state dump. The assembler enforces token budgets and logs what was included/excluded for observability.

```python
# src/shopper/memory/context_assembler.py

class ContextAssembler:
    """Builds node-specific context with token budgets and observability."""

    def __init__(self, memory_store: MemoryStore, token_budget: int = 4000):
        self.memory_store = memory_store
        self.token_budget = token_budget

    async def build_context(
        self, node_name: str, state: PlannerState, query_hint: str = ""
    ) -> AssembledContext:
        """
        Returns tailored context for a specific node.
        Logs: tokens_used, memories_retrieved, items_dropped.
        """
        ...

# Per-node context rules:
CONTEXT_RULES = {
    "meal_selector": {
        "include": ["user_profile_summary", "nutrition_plan", "schedule",
                     "top_k_memories", "preference_summary"],
        "exclude": ["raw_price_quotes", "cart_state", "audit_log"],
        "memory_query": "meal and food preferences",
        "memory_top_k": 10,
        "token_budget": 6000,
    },
    "price_optimizer": {
        "include": ["grocery_list", "budget_policy", "store_preferences",
                     "delivery_constraints"],
        "exclude": ["recipe_instructions", "nutrition_details", "meal_feedback"],
        "memory_query": "store preferences and past purchase behavior",
        "memory_top_k": 5,
        "token_budget": 4000,
    },
    "planning_critic": {
        "include": ["artifact_under_review", "evidence", "validation_results"],
        "exclude": ["full_conversation_history", "other_subgraph_scratch"],
        "memory_query": None,  # Critic doesn't use episodic memory
        "memory_top_k": 0,
        "token_budget": 3000,
    },
    "shopping_critic": {
        "include": ["artifact_under_review", "evidence", "validation_results"],
        "exclude": ["full_conversation_history", "other_subgraph_scratch"],
        "memory_query": None,
        "memory_top_k": 0,
        "token_budget": 3000,
    },
    "checkout": {
        "include": ["basket_plan", "store_account_constraints", "browser_state",
                     "verifier_rules", "approval_status"],
        "exclude": ["meal_plan_details", "nutrition_targets", "feedback_history"],
        "memory_query": "store checkout behavior and past issues",
        "memory_top_k": 3,
        "token_budget": 3000,
    },
}
```

#### Distiller (background preference summarization)

```python
# src/shopper/memory/distiller.py

class PreferenceDistiller:
    """Periodically recomputes the user's preference summary from episodic events.
    Event-sourcing pattern: append-only events → derived summary."""

    async def distill(self, user_id: str) -> UserPreferenceSummary:
        """
        1. Load all episodic memories for user (meal_feedback, store_behavior, substitution_decisions for future/manual swap feedback)
        2. Compute derived preferences:
           - cuisine_affinities: {"mediterranean": 0.8, "italian": 0.3, ...}
           - ingredient_aversions: ["cilantro", "tofu"]
           - complexity_tolerance: "medium" (derived from difficulty ratings + skip rate)
           - budget_sensitivity: "high" (derived from too_expensive feedback)
           - time_preference: "weekday_quick" (derived from schedule + cooking patterns)
        3. Write summary to Postgres (UserPreferenceSummary table)
        4. This summary is what gets loaded into state as user_preferences_learned
        """
        ...
```

#### Memory-Augmented Retrieval (MealSelector)

When MealSelector searches for recipes, it combines recipe retrieval with memory retrieval:

```python
# In meal_selector node:
async def meal_selector_node(state, config):
    context = await context_assembler.build_context("meal_selector", state,
        query_hint="meal planning preferences")

    # Recipe retrieval (Qdrant) + memory retrieval (LangGraph Store) combined
    recipes = await qdrant_store.search_recipes(
        query="high protein dinner",
        filters={"excluded_ingredients": context.dietary_restrictions},
        user_preferences=context.preference_summary,  # boosts/penalizes based on history
    )

    relevant_memories = context.retrieved_memories
    # e.g., ["Loved the Thai basil chicken (5 stars, cooked 3x)",
    #        "Said salmon was 'too fishy' — avoid strong fish",
    #        "Prefers one-pot meals on weeknights"]

    # Both recipe candidates AND relevant memories go into the prompt
    ...
```

### Core State Schema

```python
# src/shopper/agents/state.py

from typing import Annotated, TypedDict, Literal
from langgraph.graph import add_messages
import operator

class NutritionPlan(TypedDict):
    daily_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    notes: str

class MealSlot(TypedDict):
    day: str                   # "monday" .. "sunday"
    meal_type: str             # "breakfast", "lunch", "dinner", "snack"
    recipe_id: str             # Must reference real recipe in DB
    recipe_name: str
    prep_time_min: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int

class GroceryItem(TypedDict):
    name: str
    quantity: float
    unit: str
    category: str              # "produce", "dairy", "meat", "pantry", "frozen"
    already_have: bool
    best_store: str | None
    best_price: float | None
    buy_online: bool | None

class PurchaseOrder(TypedDict):
    store: str
    items: list[GroceryItem]
    total_cost: float
    delivery_fee: float
    channel: Literal["online", "in_store"]
    status: Literal["pending", "approved", "purchased", "failed"]

class CriticVerdict(TypedDict):
    passed: bool
    issues: list[str]
    warnings: list[str]
    repair_instructions: list[str]
    findings: list[dict]

class PlannerState(TypedDict):
    # Run metadata
    run_id: str
    user_id: str
    user_profile: dict

    # Agent outputs (each node writes to its section)
    nutrition_plan: NutritionPlan | None
    selected_meals: list[MealSlot]
    grocery_list: list[GroceryItem]
    store_quotes: list[StoreQuote]
    store_summaries: list[StoreSummary]
    purchase_orders: list[PurchaseOrder]
    budget_summary: BudgetSummary | None
    fridge_inventory: list[dict]

    # Critic + repair state
    critic_verdict: CriticVerdict | None
    repair_instructions: list[str]
    blocked_recipe_ids: list[str]
    avoid_cuisines: list[str]

    # Control flow
    current_phase: str
    replan_count: int
    replan_reason: str | None
    price_strategy: str | None
    price_rationale: str | None
    latest_error: str | None

    # Memory context (loaded at run start, used by ContextAssembler)
    user_preferences_learned: dict    # Derived summary from Postgres (distiller output)
    retrieved_memories: list[dict]    # Episodic memories retrieved for this run
    context_metadata: list[dict]      # Observability: tokens used, memories retrieved, items dropped per node
    trace_metadata: dict
```

### Supervisor Routing Logic

```python
# src/shopper/agents/supervisor.py

def route_from_supervisor(state: PlannerState) -> str:
    current_phase = state.get("current_phase", "memory")
    assert current_phase in {"memory", "planning", "shopping"}
    if current_phase == "shopping":
        return "shopping_subgraph"
    if current_phase == "planning":
        return "planning_subgraph"
    if state.get("replan_count", 0) > 0:
        return "planning_subgraph"
    return "load_memory"


def route_from_critic(state: PlannerState, max_replans: int = 1) -> str:
    verdict = state["critic_verdict"]
    current_phase = state.get("current_phase", "planning")
    assert current_phase in {"planning", "shopping"}
    if current_phase == "shopping":
        return "end"
    if verdict["passed"]:
        return "shopping_subgraph"
    if state["replan_count"] >= max_replans:
        return "end"
    return "planning_subgraph"
```

### Run-Centric API

```
POST   /v1/runs                    # Start a new planning run
GET    /v1/runs?user_id={user_id}&limit={n}  # List recent runs for dashboard/history
GET    /v1/runs/{run_id}           # Get run state (plan, grocery list, orders, status)
POST   /v1/runs/{run_id}/resume    # Resume paused run (approval/rejection/edits)
GET    /v1/runs/{run_id}/stream    # SSE stream of agent progress
GET    /v1/runs/{run_id}/trace     # LangSmith trace link

POST   /v1/users                   # Create user profile
GET    /v1/users/{user_id}         # Get user profile
PUT    /v1/users/{user_id}         # Update profile

POST   /v1/users/{user_id}/inventory       # Add fridge items
GET    /v1/users/{user_id}/inventory       # Get fridge contents
DELETE /v1/users/{user_id}/inventory/{id}  # Remove fridge item

POST   /v1/feedback                # Submit meal/plan feedback
```

---

## Phase 1: Foundation + Planning Subgraph + Eval Harness

**JD Coverage**: Agent architectures, prompt engineering, LangSmith tracing, Python/backend fundamentals, evaluation systems (initial)

### Deliverable
FastAPI app with run-centric API, PostgreSQL, the planning subgraph (deterministic nutrition calculation + LLM meal selector), LangSmith tracing, and initial eval harness with nutrition accuracy evaluator.

### What to Build

**1. Project scaffolding**
- `pyproject.toml` — dependencies: `langgraph`, `langchain-anthropic`, `langchain-openai`, `langsmith`, `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `python-dotenv`
- `src/shopper/config.py` — pydantic-settings loading from `.env`
- `src/shopper/main.py` — FastAPI app factory
- `docker-compose.yml` — PostgreSQL
- LangSmith tracing enabled via env vars (`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`)

**2. Database + models**
- `src/shopper/models/user.py` — `UserProfile` (age, weight_lbs, height_in, sex, activity_level, goal, dietary_restrictions, allergies, budget_weekly, household_size, cooking_skill, schedule_json)
- `src/shopper/models/run.py` — `PlanRun` (run_id, user_id, status, state_snapshot, created_at, updated_at)
- Alembic initial migration

**3. Nutrition planning (mostly deterministic)**
- `src/shopper/services/nutrition_calc.py`:
  - `calculate_tdee(profile) -> int` — Mifflin-St Jeor equation
  - `calculate_macros(tdee, goal) -> NutritionPlan` — macro splits by goal (cut: 40/30/30, bulk: 30/40/30, maintain: 30/35/35)
  - Pure functions, fully unit-testable, no LLM
- `src/shopper/agents/nodes/nutrition_planner.py` — LangGraph node that:
  - Calls `nutrition_calc` service for the math
  - Uses LLM only for edge cases: conflicting goals, unusual dietary restrictions, personalized notes
  - Writes `nutrition_plan` to state
- `src/shopper/agents/tools/nutrition_lookup.py` — `@tool` for USDA FoodData Central API (micronutrient lookups)

**4. Meal selection (LLM agent — stubbed with simple prompt for Phase 1, full retrieval in Phase 2)**
- `src/shopper/agents/nodes/meal_selector.py` — placeholder node that generates a 7-day plan from the nutrition targets
- `src/shopper/prompts/meal_selector.md` — initial prompt template

**5. Context assembler skeleton**
- `src/shopper/memory/types.py` — `EpisodicMemory`, `ContextBudget`, `AssembledContext` types
- `src/shopper/memory/context_assembler.py` — skeleton with `build_context()` method, `CONTEXT_RULES` for `nutrition_planner` and `meal_selector`
- Even in Phase 1, the nutrition planner node uses `ContextAssembler` to select which profile fields go into the prompt, rather than dumping the entire user profile
- Logs `context_metadata` (tokens used, fields included) to LangSmith trace

**6. Planning subgraph**
- `src/shopper/agents/subgraphs/planning.py` — `nutrition_planner → meal_selector` with private message history
- `src/shopper/agents/state.py` — initial `PlannerState` + `PlanningSubgraphState`

**6. Minimal top-level graph**
- Phase 1 milestone graph: `supervisor → planning_subgraph → end`
- `src/shopper/agents/supervisor.py` — initial routing logic

**7. Run-centric API**
- `src/shopper/api/routes/runs.py`:
  - `POST /v1/runs` — accepts `{user_id, profile}`, creates run, invokes graph
  - `GET /v1/runs?user_id=...&limit=...` — returns recent runs for dashboard/history views
  - `GET /v1/runs/{run_id}` — returns run state
  - `GET /v1/runs/{run_id}/trace` — returns LangSmith trace metadata/URL for UI deep-linking
- `src/shopper/api/routes/users.py` — user profile CRUD

**8. Eval harness (initial)**
- `src/shopper/evaluation/runner.py` — eval orchestrator skeleton
- `src/shopper/evaluation/datasets/nutrition_cases.json` — 20 test profiles with known-correct TDEE/macros
- `src/shopper/evaluation/evaluators/nutrition_accuracy.py`:
  - Compares agent output vs. calculated TDEE (within 5%)
  - Checks macro percentages (within 10%)
  - Checks dietary restriction compliance
- `src/shopper/validators/nutrition_validator.py` — deterministic bounds checking (calories > 1000, protein > 0, etc.)
- `scripts/run_evals.py` — CLI: `python scripts/run_evals.py --eval nutrition`
- Results upload to LangSmith as experiments

**9. Frontend — scaffolding + profile + run basics**
- `web/` — Next.js 15 project: `npx create-next-app@latest web --typescript --tailwind --app --src-dir`
- `npx shadcn@latest init` — install shadcn/ui with default theme
- Install dependencies: `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`
- `web/src/lib/api.ts` — typed API client:
  - Base URL from `NEXT_PUBLIC_API_URL` env var
  - Typed wrappers: `createUser()`, `getUser()`, `updateUser()`, `listRuns()`, `createRun()`, `getRun()`, `getRunTrace()`
  - Error handling: parse FastAPI error responses into typed errors
- `web/src/lib/types.ts` — TypeScript types mirroring backend Pydantic schemas:
  - `UserProfileCreate`, `UserProfileRead`, `UserProfileUpdate`, `RunCreateRequest`, `RunRead`, `RunStatus`
  - Keep in sync manually (small surface area in Phase 1, grow per phase)
- `web/src/app/layout.tsx` — root layout with nav shell, `QueryClientProvider`
- `web/src/app/onboarding/page.tsx` — **onboarding flow**:
  - Multi-step form: basics (age, weight, height, sex) → goals (cut/bulk/maintain) → dietary restrictions + allergies → budget + household → cooking skill + schedule
  - React Hook Form + Zod validation matching backend constraints
  - Calls `POST /v1/users` on submit → redirects to dashboard
- `web/src/app/profile/page.tsx` — **edit profile** (reuses form component, pre-populated)
- `web/src/app/page.tsx` — **dashboard** (minimal for Phase 1):
  - "Start a new meal plan" button loads the saved profile via `GET /v1/users/{user_id}` and submits `POST /v1/runs` with the full `{user_id, profile}` payload
  - Shows most recent run status via `GET /v1/runs?user_id=...&limit=1`
- `web/src/app/runs/[runId]/page.tsx` — **run detail page**:
  - Polls `GET /v1/runs/{run_id}` via TanStack Query (SSE streaming added in Phase 2)
  - Shows phase stepper: planning (active) → shopping (locked) → checkout (locked)
  - Displays nutrition plan output: daily calories, protein/carbs/fat split
  - Macro breakdown as simple bar or donut chart (Recharts)
- `web/src/components/run/phase-stepper.tsx` — visual step indicator, reused across phases
- `web/src/components/plan/nutrition-summary.tsx` — nutrition plan display card
- `web/src/hooks/use-user.ts` — TanStack Query hooks: `useUser(id)`, `useCreateUser()`, `useUpdateUser()`
- `web/src/hooks/use-run.ts` — TanStack Query hooks: `useRun(id)`, `useRuns(userId, limit?)`, `useCreateRun()`, `useRunTrace()`

**10. Tests**
- Unit: `nutrition_calc.calculate_tdee()` against hand-computed values
- Unit: `nutrition_calc.calculate_macros()` for each goal type
- Unit: `nutrition_validator` catches out-of-bounds plans
- Integration: `POST /v1/runs` → run completes → nutrition plan in state → LangSmith trace exists
- Integration: `GET /v1/runs?user_id=...&limit=1` returns the most recent run for the dashboard
- Eval: `run_evals.py --eval nutrition` passes

### Key Learnings
- LangGraph node authoring, state schema, subgraph isolation
- LangSmith tracing setup and trace inspection
- Separating deterministic logic from LLM calls
- Eval harness pattern with LangSmith experiments
- Run-centric API design for agent systems
- Next.js App Router + TanStack Query for API-driven UIs

---

## Phase 2: Recipe Retrieval + Full Meal Selection

**JD Coverage**: Retrieval pipelines, vector databases, hybrid search, reranking, context engineering

### Deliverable
Qdrant-backed hybrid recipe search with reranking. MealSelector upgraded to a real LLM agent that retrieves, evaluates, and selects recipes. Critic subgraph introduced for planning verification.

### What to Build

**1. Recipe data pipeline**
- `data/recipes/` — extract ~1000 recipes from RecipeNLG dataset (real data, not LLM-generated)
- Normalize schema: `{id, name, cuisine, ingredients[], prep_time_min, calories, protein_g, carbs_g, fat_g, tags[], instructions, source_url}`
- `src/shopper/retrieval/seed.py` — embed + upsert into Qdrant (batch processing)
- `scripts/seed_recipes.py` — CLI entry point

**2. Qdrant hybrid search**
- `src/shopper/retrieval/qdrant_store.py` — `QdrantRecipeStore`:
  - `search_recipes(query: str, filters: dict, top_k: int) -> list[ScoredRecipe]`
  - Hybrid: dense embeddings (OpenAI) + sparse BM25 vectors
  - Metadata filtering: cuisine, max_prep_time, dietary_tags, calorie_range, excluded_ingredients
  - Returns scored results with relevance scores
- `src/shopper/retrieval/embeddings.py` — embedding generation (OpenAI `text-embedding-3-small`)
- `src/shopper/retrieval/reranker.py` — cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2` or Cohere reranker)
- Docker Compose: add Qdrant service

**3. MemoryStore + load_memory node**
- `src/shopper/memory/store.py` — `MemoryStore` wrapping LangGraph Store:
  - `save_memory(user_id, category, content, metadata)` — write episodic memory
  - `recall(user_id, query, top_k, categories)` — semantic search over user's memories
  - `forget(user_id, memory_id)` — delete stale/wrong memory
  - Namespaces: `(user_id, "meal_feedback")`, `(user_id, "store_behavior")`, `(user_id, "substitution_decisions")` (future/manual swap feedback), `(user_id, "general_preferences")`
- `load_memory` node added to graph — runs at start of each run:
  - Loads canonical preferences from Postgres (`UserPreferenceSummary`)
  - Retrieves top-k relevant episodic memories from MemoryStore based on current run context
  - Writes `user_preferences_learned` and `retrieved_memories` to state
  - For new users: both are empty, which is fine

**4. MealSelector agent (upgraded) — with memory-augmented retrieval**
- `src/shopper/agents/nodes/meal_selector.py` — LLM agent that:
  - Uses `ContextAssembler.build_context("meal_selector", state)` to get tailored context (not raw state)
  - Context includes: profile summary, nutrition plan, schedule, top-k memories, preference summary
  - Makes multiple tool calls to `recipe_search` with different queries (breakfast, lunch, dinner variants)
  - Recipe search boosted/penalized by preference summary from memory
  - Relevant episodic memories injected into prompt: "User loved Thai basil chicken (5 stars)", "User said salmon was too fishy"
  - Evaluates candidates: variety (no cuisine repeat within 3 days), prep time vs. user schedule, macro fit
  - Selects 7 days x 3 meals + snacks
  - Writes `selected_meals` to state — every `recipe_id` must exist in Qdrant
- `src/shopper/agents/tools/recipe_search.py` — `@tool` wrapping `QdrantRecipeStore`
- `src/shopper/prompts/meal_selector.md` — context-engineered prompt built by ContextAssembler

**4. Critic subgraph (initial)**
- `src/shopper/agents/subgraphs/critic.py`:
  - Builds the planning boundary critic used after `planning_subgraph`
  - Worker nodes own narrow deterministic guards; the critic handles week-level macro alignment, groundedness, variety review, and optional LLM assessment
  - Outputs a single `CriticVerdict` plus structured `repair_instructions`
  - On failure: routes back into the planning subgraph rather than a standalone substitution node
- `src/shopper/validators/safety_validator.py` — checks allergies against recipe ingredients (deterministic, zero tolerance)

**5. Graph update**
- Phase 2 milestone flow: `supervisor → planning_subgraph → planning_critic_subgraph`
- Pass path ended the run at this milestone; fail path already reused the planning worker with tighter `repair_instructions`

**6. Evals (expanded)**
- `src/shopper/evaluation/datasets/meal_plan_cases.json` — 20 profiles with expected meal plan properties
- `src/shopper/evaluation/datasets/safety_cases.json` — 30 adversarial cases (allergen conflicts, "no nuts" + peanut oil, etc.)
- `src/shopper/evaluation/evaluators/meal_relevance.py`:
  - Variety score (no repeat cuisine within 3 days)
  - Prep time fits schedule
  - All recipes exist in Qdrant (groundedness)
- `src/shopper/evaluation/evaluators/safety.py`:
  - Zero tolerance: no allergens in any selected recipe
  - Tests adversarial cases
- `src/shopper/evaluation/evaluators/groundedness.py`:
  - Every recipe_id resolves to a real record
  - Nutrition facts in meal plan match source data

**7. Frontend — meal plan display + SSE streaming**
- `web/src/lib/sse.ts` — SSE utility:
  - `subscribeToRun(runId): EventSource` — connects to `GET /v1/runs/{run_id}/stream`
  - Parses typed events: `phase_started`, `phase_completed`, `node_entered`, `node_completed`, `error`, `run_completed`
  - Auto-reconnect on disconnect
- `web/src/hooks/use-run-stream.ts` — React hook wrapping SSE:
  - Merges SSE events into TanStack Query cache (run state stays fresh without polling)
  - Exposes: `status`, `currentPhase`, `events[]`, `isStreaming`
- `web/src/components/run/run-progress.tsx` — **live run progress**:
  - Phase stepper updates in real-time as SSE events arrive
  - Event log: scrolling list of agent actions ("Calculating nutrition targets...", "Searching recipes for Monday breakfast...", "Selected: Thai Basil Chicken")
  - Elapsed time per phase
- `web/src/components/plan/meal-calendar.tsx` — **7-day meal plan grid**:
  - 7 columns (Mon–Sun) × 3–4 rows (breakfast, lunch, dinner, snack)
  - Each cell is a clickable recipe card
  - Color-coded by macro fit (green = on target, yellow = slightly off, red = way off)
  - Responsive: collapses to single-day view on mobile
- `web/src/components/plan/recipe-card.tsx` — **recipe detail card**:
  - Recipe name, cuisine tag, prep time
  - Macro bar: protein / carbs / fat as stacked horizontal bar
  - Calorie count
  - Expandable: full ingredient list, instructions, source link
- `web/src/components/plan/nutrition-summary.tsx` — **upgraded**:
  - Daily macro breakdown per day (bar chart via Recharts)
  - Weekly average vs. target overlay
  - Highlight days that are over/under target
- Update `web/src/app/runs/[runId]/page.tsx`:
  - Switch from polling to SSE streaming
  - Show live progress during run, meal calendar after completion
  - "View in LangSmith" link using `GET /v1/runs/{run_id}/trace`

**8. Tests**
- Unit: Qdrant search returns relevant results for "high protein breakfast under 20 min"
- Unit: safety_validator catches peanut oil for nut-allergy user
- Integration: full run → nutrition plan → meal selection → critic passes
- Eval: `run_evals.py --eval meal_relevance,safety,groundedness` passes (safety at 100%)

### Key Learnings
- Vector DB setup, indexing, hybrid search (dense + sparse)
- Retrieval pipeline: embed → search → filter → rerank
- Context engineering: fitting profile + plan + schedule + preferences into prompt window
- Critic pattern: verification gate between subgraphs
- Safety-critical evaluation (zero tolerance)
- SSE integration with React for real-time agent progress

---

## Phase 3: Grocery List + Fridge Inventory

**JD Coverage**: Tool calling, multi-step reasoning, deterministic services in agent pipelines

### Deliverable
Deterministic grocery list builder that extracts ingredients, diffs against fridge, aggregates quantities, and categorizes. Shopping subgraph introduced.

### What to Build

**1. Ingredient aggregation service (deterministic)**
- `src/shopper/services/ingredient_aggregator.py`:
  - `extract_ingredients(meals: list[MealSlot], recipe_db) -> list[RawIngredient]` — pull ingredients from recipe records
  - `aggregate_quantities(ingredients: list[RawIngredient]) -> list[AggregatedItem]` — combine duplicates, convert units
  - `diff_against_fridge(items: list[AggregatedItem], fridge: list[FridgeItem]) -> list[GroceryItem]` — mark `already_have`
  - `categorize(items: list[GroceryItem]) -> list[GroceryItem]` — assign produce/dairy/meat/pantry/frozen
  - Unit conversion library: grams↔oz, cups↔ml, tsp↔tbsp, etc.
  - Pure functions, fully unit-testable

**2. Fridge inventory**
- `src/shopper/models/inventory.py` — `FridgeItem` (user_id, name, quantity, unit, category, expiry_date)
- `src/shopper/api/routes/inventory.py` — CRUD endpoints
- `src/shopper/agents/tools/inventory_tools.py` — `get_fridge_contents()`, `update_fridge_item()`, `remove_fridge_item()` as `@tool`

**3. Grocery builder node (deterministic)**
- `src/shopper/agents/nodes/grocery_builder.py` — LangGraph node that:
  - Reads `selected_meals` from state
  - Calls `ingredient_aggregator` service (not LLM)
  - Calls `get_fridge_contents()` tool for inventory
  - Writes `grocery_list` to state
  - No LLM call — this is pure code in a graph node

**4. Shopping subgraph**
- `src/shopper/agents/subgraphs/shopping.py` — `grocery_builder → price_optimizer` with private message history

**5. Graph update**
- Current flow: `supervisor → load_memory → planning_subgraph → planning_critic_subgraph → shopping_subgraph → shopping_critic_subgraph → end`
- Shopping worker nodes own deterministic grocery-building and pricing guards; the shopping critic runs once at the boundary after the full shopping subgraph

**6. Evals (expanded)**
- `src/shopper/evaluation/datasets/grocery_cases.json` — 15 meal plans with expected grocery lists
- `src/shopper/evaluation/evaluators/grocery_completeness.py`:
  - Every recipe ingredient appears in grocery list (or marked `already_have`)
  - Quantities are sufficient (not under-counted)
  - No phantom items (items not in any recipe)
  - Unit conversions are correct

**7. Frontend — fridge inventory + grocery list**
- `web/src/hooks/use-inventory.ts` — TanStack Query CRUD hooks:
  - `useInventory(userId)` — fetches `GET /v1/users/{user_id}/inventory`
  - `useAddInventoryItem()` — `POST`, with optimistic update
  - `useDeleteInventoryItem()` — `DELETE`, with optimistic update
- `web/src/app/inventory/page.tsx` — **fridge inventory page**:
  - Table/list of current fridge items: name, quantity, unit, category, expiry date
  - "Add item" form (inline or modal): name, quantity, unit, category, expiry
  - Delete button per item with confirmation
  - Visual indicator for items expiring soon (< 3 days = yellow, expired = red)
  - Category filter tabs: produce, dairy, meat, pantry, frozen
- `web/src/components/inventory/inventory-manager.tsx` — reusable inventory CRUD component
- `web/src/components/grocery/grocery-list.tsx` — **grocery list display**:
  - Grouped by category (produce, dairy, meat, pantry, frozen)
  - Each item shows: name, quantity, unit
  - Items marked `already_have` shown as struck-through with "In fridge" badge
  - Summary: total items needed, items already owned
- Update `web/src/app/runs/[runId]/page.tsx`:
  - After meal plan section, show grocery list section (appears when shopping phase completes)
  - "Edit fridge" link → inventory page (so user can update before next run)
- Add inventory link to nav

**8. Tests**
- Unit: `aggregate_quantities` handles "2 cups milk" + "1.5 cups milk" = "3.5 cups milk"
- Unit: `diff_against_fridge` correctly marks owned items
- Unit: unit conversion edge cases (grams to oz, teaspoons to tablespoons)
- Integration: full run → plan → meals → grocery list with fridge diff
- Eval: `run_evals.py --eval grocery_completeness` passes

### Key Learnings
- When NOT to use an LLM (this node is pure code)
- Tool integration for data access within graph nodes
- Deterministic service design in agent pipelines
- Optimistic updates with TanStack Query for responsive CRUD UIs

---

## Phase 4: Price Optimization + Store Comparison

**JD Coverage**: Parallel fan-out/fan-in, third-party API integrations, cost optimization, tool-calling protocols

### Deliverable
Price optimizer with parallel store queries (1 real + 2 mock), deterministic price ranking, and LLM-assisted tradeoff decisions for online vs. in-store splits. Budget-triggered replanning.

### What to Build

**1. Store adapter interface**
- `src/shopper/agents/tools/store_scraper.py`:
  - `StoreAdapter` protocol: `async def search_prices(items: list[str]) -> list[StoreQuote]`
  - `InstacartAdapter` — 1 real integration (Playwright-based scraping or Instacart API if available)
  - `MockWalmartAdapter` — realistic mock with price variance
  - `MockCostcoAdapter` — realistic mock with bulk pricing
  - Each returns: `StoreQuote(item, price, unit_price, in_stock, delivery_fee, min_order)`
- Rate limiting, retry logic, timeout handling per adapter

**2. Price ranking service (deterministic)**
- `src/shopper/services/price_ranker.py`:
  - `rank_by_price(quotes: dict[str, list[StoreQuote]]) -> list[GroceryItem]` — cheapest per item
  - `calculate_store_totals(items, quotes) -> dict[str, StoreSummary]` — total per store including delivery fees
  - Pure sort + math — no LLM

**3. Budget checking service (deterministic)**
- `src/shopper/services/budget_checker.py`:
  - `check_budget(orders: list[PurchaseOrder], budget: float) -> BudgetResult`
  - Returns pass/fail + overage amount

**4. Price optimizer node (deterministic ranking + LLM tradeoff)**
- `src/shopper/agents/nodes/price_optimizer.py` — LangGraph node that:
  - Reads `grocery_list` from state
  - **Fan-out**: `asyncio.gather` across all store adapters (parallel)
  - **Fan-in**: aggregates quotes
  - Calls `price_ranker` service for cheapest-per-item (deterministic)
  - Calls LLM for the **tradeoff decision only**: given user preferences, delivery fees, time value, store proximity — how to split online vs. in-store?
  - Calls `budget_checker` — if over budget, sets `replan_reason` on state
  - Writes `purchase_orders` to state
- `src/shopper/prompts/price_tradeoff.md` — prompt for the online/in-store split decision

**5. Repair via existing worker + critic loop**
- `src/shopper/agents/nodes/price_optimizer.py` writes `replan_reason` when the cheapest available basket is still incomplete or over budget
- `src/shopper/agents/nodes/shopping_critic.py` turns final shopping failures into structured `repair_instructions`
- No standalone `substitution.py` exists in the current repo; budget and availability issues stay inside the existing planning/shopping replan story

**6. Graph update**
- Full shopping subgraph: `grocery_builder → price_optimizer`
- Planning critic runs after the planning subgraph; shopping critic runs after the shopping subgraph
- Planning failures route back through a bounded planning replan loop
- Shopping failures currently end the run with structured `critic_verdict`, `repair_instructions`, and `replan_reason`
- `supervisor → load_memory → planning_subgraph → planning_critic_subgraph → shopping_subgraph → shopping_critic_subgraph → end`

**7. Evals (expanded)**
- `src/shopper/evaluation/datasets/price_cases.json` — 15 cases with mock quotes and expected optimization decisions
- `src/shopper/evaluation/evaluators/price_optimality.py`:
  - Agent picked cheapest per item (or justified deviation)
  - Total within budget
  - Online/in-store split is reasonable given user preferences
- Repair-path evals: over-budget or unavailable baskets surface actionable `repair_instructions` / `replan_reason`

**8. Frontend — price comparison + budget tracking**
- `web/src/components/grocery/price-table.tsx` — **store price comparison**:
  - Table: rows = grocery items, columns = stores (Instacart, Walmart, Costco)
  - Each cell shows price, highlight cheapest per item (green)
  - Out-of-stock items marked with badge
  - Column footer: store total + delivery fee = grand total per store
  - Recommended split indicator: items tagged "buy online" vs. "buy in store"
- `web/src/components/grocery/budget-bar.tsx` — **budget indicator**:
  - Horizontal progress bar: total cost vs. weekly budget
  - Green/yellow/red thresholds (< 80% / 80-100% / over budget)
  - If over budget: shows overage amount + "Agent is finding alternatives..." during replan
- `web/src/components/grocery/purchase-orders.tsx` — **purchase order summary**:
  - Card per store with: store name, item count, subtotal, delivery fee, channel (online/in-store)
  - Combined total across all orders
  - Status badge per order: pending → approved → purchased
- Update `web/src/app/runs/[runId]/page.tsx`:
  - After grocery list section, show price comparison + purchase orders
  - Budget bar visible throughout shopping phase
  - During critic-driven replan/failure handling: show "Replanning..." indicator with reason

**9. Tests**
- Unit: `price_ranker` picks cheapest per item correctly
- Unit: `budget_checker` catches over-budget scenarios
- Unit: fan-out completes within timeout, handles partial adapter failures gracefully
- Integration: full run with mock stores → optimized purchase orders
- Integration: over-budget → shopping critic failure surfaces actionable `repair_instructions` / `replan_reason`
- Eval: `run_evals.py --eval price_optimality,safety` passes

### Key Learnings
- Parallel fan-out/fan-in in async Python within LangGraph
- Adapter pattern for heterogeneous external services
- Knowing where to use LLM (tradeoff reasoning) vs. code (price sorting)
- Replanning loops with iteration caps
- Error handling for unreliable external services
- Data table patterns for multi-dimensional comparison UIs

---

## Phase 5: Browser Checkout + Human Approval

**JD Coverage**: Agent reliability, human-in-the-loop, governance, exception handling, browser automation

### Deliverable
browser-use agent for cart building with deterministic verification gates, `interrupt_before` for human approval, Playwright fallback, and full audit logging.

### What to Build

**1. Browser agent tools**
- `src/shopper/agents/tools/browser_tools.py`:
  - `build_cart(store: str, items: list[GroceryItem]) -> CartBuildResult` — uses browser-use to:
    - Navigate to store site
    - Search for each item
    - Add to cart with correct quantity
    - Returns cart state + screenshot
  - `apply_coupons(store: str) -> list[AppliedCoupon]` — browser-use searches for applicable coupons
  - `complete_checkout(store: str) -> OrderConfirmation` — browser-use completes checkout flow
  - Auth state: Playwright `storage_state` for session persistence, loaded from encrypted env/secret
  - Screenshot capture at each major step

**2. Cart verifier (deterministic)**
- `src/shopper/agents/tools/cart_verifier.py`:
  - After browser-use builds cart, Playwright reads the page state
  - `verify_cart(expected_items, page) -> CartVerification`:
    - Item count matches
    - Quantities correct
    - Subtotal within 2% of expected
    - No unexpected items
    - Delivery fee matches quote
  - Returns pass/fail with discrepancy details

**3. Checkout subgraph**
- `src/shopper/agents/subgraphs/checkout.py`:
  - Node 1: `browser_cart_builder` — browser-use builds cart
  - Node 2: `cart_verifier` — deterministic verification (if fail → retry once, then fallback)
  - Node 3: **`interrupt_before`** — pauses for human approval, sends cart summary + screenshot
  - Node 4: `checkout_executor` — browser-use completes purchase (only after approval)
  - Node 5: `post_checkout_verifier` — confirms order went through
  - Fallback: if browser-use fails 2x, drop to "manual review" state (user gets shopping list + store link)
  - Safety constraints: max $200 per order, max $500 per week, never auto-approve

**4. Human approval flow**
- `POST /v1/runs/{run_id}/resume` with body `{"decision": "approve" | "reject", "edits": {...}}`
- Resumes graph via `AsyncPostgresSaver` checkpointer
- On rejection: marks order failed and can feed future critic-driven replanning work; there is no standalone substitution step today

**5. Audit logging**
- `src/shopper/models/audit.py` — `AuditLog` (timestamp, run_id, user_id, agent, action, input_summary, output_summary, screenshot_path, cost_usd, latency_ms)
- Log every action: cart_created, items_added, cart_verified, approval_requested, approved/rejected, checkout_attempted, checkout_confirmed, checkout_failed
- `src/shopper/models/order.py` — `PurchaseOrder` table with full status tracking

**6. Evals (expanded)**
- `src/shopper/evaluation/datasets/browser_cases.json` — 10 test scenarios (normal checkout, item not found, wrong quantity, stale page)
- `src/shopper/evaluation/evaluators/browser_accuracy.py`:
  - Cart accuracy: all intended items present, quantities match
  - Subtotal accuracy: within 2% of quoted price
  - Fee accuracy: delivery fee matches expectation
  - Recovery rate: browser-use self-recovers on minor issues
  - Approval compliance: 100% human approval before checkout

**7. Frontend — checkout approval gate + run history**
- `web/src/app/runs/[runId]/approve/page.tsx` — **checkout approval page** (the critical human-in-the-loop screen):
  - Navigated to automatically when SSE emits `approval_requested` event
  - Shows per-store cart review:
    - Cart items table: item name, quantity, unit price, line total
    - Cart screenshot (rendered from `cart_screenshot_path` via backend)
    - Cart verification status: passed/failed with discrepancy details
    - Subtotal, delivery fee, total
  - Spending guardrail display: "This order: $X / Your weekly limit: $Y"
  - **Action buttons**:
    - "Approve" → `POST /v1/runs/{run_id}/resume` with `{"decision": "approve"}`
    - "Reject" → confirmation dialog with optional reason → `POST /v1/runs/{run_id}/resume` with `{"decision": "reject"}`
    - "Edit" → inline item removal/quantity adjustment → `POST /v1/runs/{run_id}/resume` with `{"decision": "approve", "edits": {...}}`
  - Clear warning: "Approving will complete the purchase. This cannot be undone."
- `web/src/components/checkout/cart-review.tsx` — cart contents display component
- `web/src/components/checkout/approval-gate.tsx` — approve/reject/edit controls
- `web/src/app/runs/page.tsx` — **run history page**:
  - List of all past runs, newest first
  - Each row: date, status (completed/failed/awaiting approval), meal count, total cost
  - Click → navigates to run detail page
  - Filter by status
  - Runs awaiting approval highlighted with badge
- `web/src/components/run/run-card.tsx` — run summary card for history list
- Update nav: add "History" link
- **Notification**: when a run reaches approval state, show a toast/banner on any page: "Your cart is ready for review" with link to approval page

**8. Tests**
- Integration: browser-use against a mock store page (local Playwright test server)
- Test: `interrupt_before` pauses execution, `POST /v1/runs/{run_id}/resume` with approval continues
- Test: `POST /v1/runs/{run_id}/resume` with rejection stops, records reason
- Test: spending limit blocks checkout over threshold
- Test: cart verifier catches wrong quantity, triggers retry
- Test: 2x browser-use failure → graceful fallback to manual mode
- Eval: `run_evals.py --eval browser_accuracy` — approval compliance at 100%

### Key Learnings
- LLM-controlled browser agent (browser-use) for flexible UI navigation
- Deterministic verification wrapping autonomous actions
- Human-in-the-loop with `interrupt_before` + durable checkpointing
- Governance: spending limits, approval gates, audit trails
- Bounded autonomy: agent navigates, code verifies, human approves
- Fallback design: graceful degradation when automation fails
- Building trust through UI: showing verification results + screenshots before irreversible actions

---

## Phase 6: Feedback Loops + Memory Pipeline + Preference Learning

**JD Coverage**: Feedback loops for learning from human corrections, agent improvement over time, context engineering, memory management

### Deliverable
Full memory write pipeline: feedback → episodic memory → background distillation → preference summary. Memory-augmented retrieval produces measurably better plans for returning users.

### What to Build

**1. Feedback system**
- `src/shopper/models/feedback.py` — `UserFeedback`:
  - `(user_id, run_id, recipe_id, rating 1-5, feedback_type, comment, created_at)`
  - feedback_type enum: "taste", "difficulty", "portion_size", "would_repeat", "too_expensive", "skipped"
- `src/shopper/api/routes/feedback.py`:
  - `POST /v1/feedback` — submit feedback on individual meals or overall plan
  - Accepts both explicit (ratings, comments) and implicit (meal was skipped/cooked)

**2. Feedback → episodic memory pipeline**
- `src/shopper/agents/nodes/feedback_processor.py`:
  - On feedback submission, writes episodic memories to MemoryStore:
    - `(user_id, "meal_feedback")`: "Rated Thai basil chicken 5/5, comment: 'family loved it, will make again'"
    - `(user_id, "substitution_decisions")`: "Rejected a cheaper fish swap during manual replan, reason: 'tilapia tastes bland'"
    - `(user_id, "general_preferences")`: "Marked 3 Italian meals as 'skipped' in week 5"
  - Mostly deterministic aggregation for structured feedback
  - LLM used to extract nuanced preferences from free-text comments (e.g., "too much cleanup" → memory: "dislikes high-cleanup recipes")
  - **Write policy enforced**: only trusted signals become memories, never raw model reasoning

**3. Preference distiller (background)**
- `src/shopper/memory/distiller.py` — `PreferenceDistiller`:
  - Runs after feedback is submitted (not during planning runs)
  - Loads all episodic memories for user
  - Computes derived `UserPreferenceSummary`:
    - `cuisine_affinities`: {"mediterranean": 0.8, "italian": 0.3}
    - `ingredient_aversions`: ["cilantro", "tofu", "strong fish"]
    - `complexity_tolerance`: "medium" (from difficulty ratings + skip rate)
    - `budget_sensitivity`: "high" (from "too_expensive" feedback frequency)
    - `time_preference`: "weekday_quick" (from schedule + cooking patterns)
  - Writes summary to Postgres (`UserPreferenceSummary` table)
  - **Event-sourcing pattern**: summary is always recomputed from events, never hand-edited by model
  - **Conflict policy**: newer explicit statements override older inferred preferences
  - **Recency weighting**: recent feedback weighted more heavily than old feedback

**4. Feedback-informed retrieval**
- Update `QdrantRecipeStore.search_recipes()`:
  - Accept `user_preferences` parameter (from distilled summary)
  - Boost recipes matching preferred cuisines
  - Penalize recipes with disliked ingredients
  - Filter out recipes rated 1-2 stars by this user
  - Reranker considers preference alignment as a signal

**5. Implicit feedback tracking**
- Track which meals from a plan were actually cooked (user marks in app or doesn't)
- Skip rate per recipe type informs future complexity/time estimates
- Purchase completion rate: did the user actually buy and cook the plan?
- Cart edits (user repeatedly removes an item) → inferred aversion memory
- All implicit signals written as episodic memories with `source: "implicit"`

**6. Full memory-augmented feedback loop in graph**
- After a run completes, feedback can be submitted via API
- Feedback processor writes episodic memories → distiller updates preference summary
- Next run's `load_memory` node loads fresh summary + retrieves relevant episodic memories
- MealSelector's `ContextAssembler` injects both summary and specific memories into prompt
- Example assembled context: "Preference summary: Mediterranean-leaning, avoids cilantro, prefers <30min weekday meals. Relevant memories: 'Loved the Thai basil chicken (5 stars, cooked 3x)', 'Said the homemade pasta had too much cleanup', 'Rejected salmon→tilapia sub last week'"

**7. Evals (expanded)**
- `src/shopper/evaluation/datasets/memory_cases.json` — 20 multi-session scenarios
- `src/shopper/evaluation/evaluators/memory_quality.py`:
  - **Allergy/restriction recall**: planner remembers allergies from memory (safety-critical)
  - **Relevant memory retrieval**: retrieved memories are actually relevant to current planning context (precision)
  - **Stale preference handling**: user changed mind → system adapts (newer overrides older)
  - **Preference impact**: plans for users with 5 weeks of history are measurably more aligned than week 1
  - **Safety preservation**: memory-driven changes don't violate dietary restrictions
- Eval: user with 5 weeks of negative Italian food ratings → next plan has fewer Italian meals
- Eval: user marks recipe as "never again" → recipe never appears again
- Eval: user with "difficulty: too hard" pattern → simpler recipes selected
- Eval: conflicting feedback (liked Italian week 1, disliked week 5) → recency wins

**8. Frontend — feedback + preference learning visualization**
- `web/src/app/feedback/[runId]/page.tsx` — **post-run feedback page**:
  - Shows completed meal plan as a card grid
  - Per-meal feedback widget:
    - Star rating (1-5)
    - Quick tags: "Too hard", "Too expensive", "Wrong portion", "Would repeat", "Skipped"
    - Optional free-text comment
  - Overall plan feedback: "How was this week's plan?" (1-5 stars + comment)
  - Submit calls `POST /v1/feedback` for each rated meal
  - Thank-you state: "Your feedback helps improve future plans"
- `web/src/components/feedback/meal-rating.tsx` — star rating + tag + comment component
- `web/src/components/feedback/preference-dashboard.tsx` — **learned preferences display**:
  - Shows what the system has learned about the user (from distilled `UserPreferenceSummary`):
    - Cuisine affinities as horizontal bar chart (Mediterranean: 80%, Italian: 30%, ...)
    - Ingredient aversions as tag list
    - Complexity tolerance, budget sensitivity, time preference as labeled badges
  - "The system remembers" section: recent episodic memories as a timeline
    - "Loved Thai basil chicken (5 stars, cooked 3x)"
    - "Said salmon was too fishy"
    - "Prefers one-pot meals on weeknights"
  - User can delete individual memories ("Forget this")
- Add preference dashboard to profile page as a tab/section
- Update run detail page: add "Give feedback" button after run completes (links to feedback page)
- Update dashboard: show "Feedback pending" badge for completed runs without feedback

**9. Tests**
- Unit: feedback processor writes correct episodic memories
- Unit: distiller computes correct cuisine affinities from event history
- Unit: ContextAssembler respects token budget, drops low-relevance memories first
- Unit: Qdrant search boosts preferred cuisines, penalizes disliked
- Unit: conflict resolution — newer explicit > older inferred
- Integration: submit feedback → distiller runs → next run produces different results
- Integration: "never again" recipe excluded from all future searches
- Integration: context_metadata logged to LangSmith shows memory retrieval stats

### Key Learnings
- Memory system design: episodic events + derived summaries (event-sourcing pattern)
- Memory write policy: only trusted signals, no model chain-of-thought
- Memory conflict resolution: recency + explicit > inferred
- Context assembly: per-node context building with token budgets
- Memory-augmented retrieval: combining recipe search with user memory
- Background distillation: append-only events → compact preference profile
- Preference learning without fine-tuning (retrieval + memory + prompt context)
- Making AI memory transparent: showing users what the system remembers builds trust and invites correction

---

## Phase 7: Cost Optimization + Production Hardening

**JD Coverage**: Inference cost/latency optimization, observability, governance, enterprise AI

### Deliverable
Model routing for cost reduction, Redis caching, full observability dashboard via LangSmith, and production hardening.

### What to Build

**1. Model routing**
- `src/shopper/agents/model_router.py`:
  - High-stakes (planning/shopping critic review, groundedness) → Claude Sonnet
  - Medium (meal selection, price tradeoff) → Claude Sonnet
  - Simple (preference extraction from comments, formatting) → Claude Haiku
  - browser-use: uses its own model selection (optimize for vision tasks)
  - Track cost per node per run in LangSmith metadata
- Goal: 40-60% cost reduction vs. using Sonnet for everything

**2. Caching**
- Add Redis to Docker Compose
- Cache layers:
  - Nutrition facts (USDA data) — TTL: 30 days
  - Recipe embeddings — TTL: indefinite (invalidate on re-seed)
  - Store price quotes — TTL: 1 hour
  - Identical retrieval queries — TTL: 24 hours
- Track cache hit rate in LangSmith custom metadata

**3. Latency optimization**
- SSE streaming: `GET /v1/runs/{run_id}/stream` streams agent progress events
- Parallel store queries already in Phase 4 — measure and optimize
- Profile end-to-end: identify bottleneck nodes, optimize slowest ones
- Target: planning phase < 20s, shopping phase < 15s per store

**4. Comprehensive eval dataset**
- Expand all datasets to 100-150 total scenarios
- Add regression tests: every prompt change must not regress eval scores
- LangSmith experiments: compare prompt versions side by side
- CI integration: evals run on PR, block merge if safety < 100% or other evals regress > 5%
- **Memory evals (advanced)**: cross-user leakage test (user A's memories never appear in user B's context), distillation quality (summary preserves important corrections from events), context budget compliance (no node exceeds its token budget)

**5. Online monitoring**
- `src/shopper/evaluation/monitors/online_monitor.py`:
  - Hook into LangSmith traces for all production runs
  - Alert on: latency spikes, cost spikes, safety violations, error rate increase, groundedness regression
  - Weekly summary: runs completed, avg cost, eval scores, user satisfaction

**6. Audit trail + governance (full)**
- `src/shopper/models/audit.py` fully populated from Phase 5
- Add: cost tracking per run, model used per node, token counts
- Spending dashboard: total spent per user per week, per store
- Configurable spending limits per user
- Data retention: audit logs kept 90 days, auto-cleanup

**7. Production hardening**
- Rate limiting on all API endpoints
- Input validation: reject nonsensical profiles (weight < 50 lbs, budget < $10, etc.)
- Graceful degradation: store adapter failure → proceed with remaining stores
- Health check: `GET /health` verifies DB, Qdrant, Redis, LangSmith connectivity
- Docker Compose for full stack: API + Postgres + Qdrant + Redis

**8. Frontend — polish, loading states, cost dashboard**
- **Loading & error states across all pages**:
  - Skeleton loaders (shadcn `Skeleton`) for every data-dependent component
  - Error boundaries with retry buttons
  - Empty states with helpful CTAs ("No runs yet — start your first meal plan")
  - Toast notifications for async operations (feedback submitted, inventory updated)
- `web/src/components/run/cost-summary.tsx` — **per-run cost display**:
  - Total grocery cost, delivery fees, savings from optimization
  - Cost trend chart: weekly spending over time (Recharts line chart)
  - Token/LLM cost per run (from audit log, if user opts in to seeing it)
- **Dashboard upgrades** (`web/src/app/page.tsx`):
  - Weekly summary: runs this week, total spent, upcoming meal plan
  - Quick actions: "Plan this week", "Update fridge", "View history"
  - Spending widget: weekly spend vs. budget (reuses budget-bar)
- **Responsive design pass**:
  - All pages usable on mobile (375px+)
  - Meal calendar collapses to day-by-day swipe view
  - Grocery list stacks columns on narrow screens
  - Checkout approval works on phone (critical — user might approve from notification)
- **Accessibility pass**:
  - Keyboard navigation for all interactive elements
  - ARIA labels on charts and custom components
  - Color contrast compliance (WCAG AA)
  - Screen reader support for phase stepper and progress updates
- **Dark mode**: shadcn/ui dark theme toggle (already supported, just wire it up)

**9. Tests**
- Test: model routing produces correct model per node type
- Test: cache hit returns same result, reduces API calls
- Test: rate limiting returns 429
- Test: graceful degradation on partial store failure
- Load test: concurrent runs don't interfere with each other
- Eval: full suite at 100-150 cases, safety at 100%, others > 90%

### Key Learnings
- Model routing strategies for cost reduction
- Caching patterns for LLM applications
- Production observability for AI systems
- Governance and audit trails (enterprise AI readiness)
- CI/CD integration for eval-gated deployments
- Production frontend polish: loading states, error handling, responsive design, accessibility

---

## JD Coverage Summary

| JD Requirement | Phase(s) | How |
|---|---|---|
| Agent architectures (multi-step, tool calling, exception handling) | 1-5 | Subgraph orchestration, tool calling, browser automation, error recovery |
| Evaluation systems (quality, accuracy, safety, groundedness) | 1-7 | Eval harness from Phase 1, expanded every phase, CI-gated |
| Prompt systems, retrieval pipelines, context engineering | 1, 2, 6 | Hybrid search, reranking, ContextAssembler per node, token budgets |
| Context engineering for reliable agent behavior | 1-7 | ContextAssembler with per-node rules, memory retrieval, token budget observability |
| Feedback loops for learning from corrections | 6 | Episodic memory pipeline, preference distillation, memory-augmented retrieval |
| Optimize inference cost and latency | 7 | Model routing, caching, parallel execution, context budget enforcement |
| Agent reliability, observability, governance | 5, 7 | Approval gates, audit trail, LangSmith monitoring, memory write policy |
| LangGraph | 1-7 | StateGraph, subgraphs, interrupts, checkpoints, Store for long-term memory |
| Vector databases, reranking, hybrid search | 2 | Qdrant hybrid (dense + sparse), cross-encoder reranking |
| MCP, tool-calling protocols, API integrations | 3, 4 | Tool definitions, store adapters, USDA API |
| Evaluation frameworks, continuous monitoring | 1-7 | LangSmith experiments, online monitoring, CI gates, memory evals |
| Enterprise AI (compliance, audit trails, governance) | 5, 7 | Spending limits, approval gates, audit log, data retention |
| Full-stack delivery (demo-ready) | 1-7 | Next.js frontend built alongside each backend phase, SSE streaming, human-in-the-loop approval UI |

---

## Verification Strategy

After each phase:

1. **Run end-to-end**: `POST /v1/runs` with test profile → verify all state fields populated correctly
2. **Check LangSmith**: traces show correct subgraph flow, no errors, reasonable latency
3. **Run evals**: `python scripts/run_evals.py` — all evaluators for completed phases pass
4. **Safety check**: `run_evals.py --eval safety` at 100% (every phase, non-negotiable)
5. **Manual test**: create a real meal plan for yourself, inspect quality
6. **Cost check**: review LangSmith cost per run — track trend over phases

## Browser Agent Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Cart accuracy | 100% items match intent | Deterministic cart verifier |
| Subtotal accuracy | Within 2% of quoted | Verifier total vs. quoted sum |
| Recovery rate | >80% self-recovery | browser-use retries that succeed without fallback |
| Failure containment | 0 unintended purchases | Approval gate compliance — never auto-checkout |
| Approval compliance | 100% | Every checkout preceded by human approval |
| UI change resilience | Tracked, not gated | Periodic runs against live site, measure breakage |
