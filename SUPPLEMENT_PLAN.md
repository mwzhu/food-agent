# Supplement Agent — Implementation Plan

## Context

Pivot from grocery/meal-planning to a supplement comparison + purchasing agent. Uses Shopify Storefront MCP (live, no auth, every Shopify store) for product discovery, comparison, cart building, and checkout handoff. Fully isolated from the existing grocery codebase — separate module, separate DB table, separate API routes, separate frontend pages.

**Demo target:** a16z pitch in ~48 hours.

**Minimum viable demo:** Health form → MCP search across real stores → LLM comparison → recommended stack → real cart URLs that open Shopify checkout with items in cart.

---

## Design Decisions (Locked)

1. **Full isolation.** `src/shopper/supplements/` is self-contained. No modifications to existing grocery code.
2. **Single end-to-end run.** No chained run types. One run: intake → discover → analyze → critique → checkout.
3. **Multi-store carts from day 1.** Checkout produces `list[StoreCart]`, each with its own checkout URL.
4. **Dedicated `supplement_runs` table.** Cart/snapshot state lives inside snapshot JSON. No FK coupling to grocery order/audit tables.
5. **Carts are created before approval.** The graph builds carts and checkout URLs first, then pauses for approval.
6. **Approval does not resume the graph.** `/approve` records which stores were approved, marks the run complete, and surfaces the already-created checkout URLs. No graph resume complexity.
7. **Supplement event models are local.** Do not reuse grocery `PhaseName` / `RunEvent` types because supplement phases are different.
8. **Start with 2-3 verified stores, expand after spike.** Some stores may restrict MCP access.
9. **Critic can abstain.** If user has medications/conditions with interaction risk, return "manual review needed" instead of forcing a confident recommendation.
10. **Duplicate UI components shamelessly.** No genericizing grocery components for the demo.

---

## Folder Structure

```
src/shopper/supplements/
├── __init__.py
├── events.py                     # SupplementEvent, emit_supplement_event, bind_event_emitter
├── agents/
│   ├── __init__.py
│   ├── graph.py                  # build_supplement_graph, invoke_supplement_graph
│   ├── supervisor.py             # routing logic
│   ├── state.py                  # SupplementRunState + subgraph states
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── health_goal_analyzer.py
│   │   ├── store_searcher.py     # parallel MCP search
│   │   ├── ingredient_comparator.py
│   │   ├── stack_builder.py
│   │   ├── supplement_critic.py
│   │   └── mcp_cart_builder.py
│   ├── subgraphs/
│   │   ├── __init__.py
│   │   ├── discovery.py          # goal_analyzer → store_searcher
│   │   ├── analysis.py           # comparator → stack_builder
│   │   ├── critic.py
│   │   └── checkout.py           # cart builder (no graph resume)
│   └── tools/
│       ├── __init__.py
│       └── shopify_mcp.py        # MCP client
├── schemas/
│   ├── __init__.py
│   ├── health.py                 # HealthProfile
│   ├── product.py                # ShopifyProduct, ProductComparison
│   ├── recommendation.py         # SupplementStack, StoreCart
│   └── run.py                    # SupplementStateSnapshot, phase types
├── models/
│   ├── __init__.py
│   └── run.py                    # SupplementRun (dedicated table)
└── api/
    ├── __init__.py
    └── routes.py                 # /v1/supplements/* endpoints

web/src/app/supplements/
├── page.tsx                      # Health profile form
└── [runId]/
    └── page.tsx                  # Run detail with comparison + checkout

web/src/components/supplements/
├── health-form.tsx
├── product-comparison.tsx
├── stack-recommendation.tsx
└── checkout-links.tsx
```

---

## Imports from Existing Code (Read-Only, No Modifications)

| Module | What | Why |
|---|---|---|
| `shopper.agents.llm` | LLM config / model init | Same Claude models |
| `shopper.memory.store` | `MemoryStore` (optional, only if time permits) | User preference recall |
| `shopper.config` | `Settings` base | Extend with supplement-specific settings |
| `shopper.db` | `create_engine`, `create_session_factory` | Shared DB connection bootstrap |
| `shopper.api.routes.stream` | SSE streaming pattern (reference, copy the shape) | Same transport pattern, but supplement-local event types |

**Do not reuse directly:** grocery `PhaseName`, `RunEvent`, `emit_run_event`, `ContextAssembler`, `RunManager`, `PlannerStateSnapshot`.

---

## Tasks

### Task 0: MCP Spike — Verify Shopify MCP Works (BLOCKING)
> Everything else depends on this. If MCP doesn't work, pivot immediately.

- [x] **0a.** Write `shopify_mcp.py` with three functions:
  - `search_store(store_domain, query) → list[product]`
  - `update_cart(store_domain, variant_id, quantity, cart_id=None) → cart_result`
  - `get_cart(store_domain, cart_id) → cart_result`
- [x] **0b.** Test `search_store` against 3 stores: `ritual.com`, `transparentlabs.com`, `livemomentous.com`
  - Verify: returns product names, prices, variant IDs, descriptions
  - If a store blocks/errors, try alternatives: `goli.com`, `vitalproteins.com`, `mudwtr.com`
- [x] **0c.** Test `update_cart` — create a cart (no cart_id) with a real variant ID from search results
  - Verify: returns cart_id and checkout_url
  - Verify: checkout_url opens a real Shopify checkout page with the item in cart
- [x] **0d.** Lock the list of 2-3 verified working stores for the demo

**Verified on April 9, 2026 (America/Los_Angeles):**
- `ritual.com` — search query `sleep` → `Day & Night Support Ritual*` cart + checkout verified
- `transparentlabs.com` — search query `creatine hmb` → `Creatine HMB Travel Packs` cart + checkout verified
- `livemomentous.com` — search query `magnesium l-threonate` → `Magnesium L-Threonate` cart + checkout verified

Artifacts:
- `src/shopper/supplements/tools/shopify_mcp.py`
- `scripts/verify_shopify_mcp.py`
- `data/examples/shopify_mcp_spike_results.json`

**Exit criteria:** We have a working MCP client and 2-3 confirmed stores where search → cart → checkout URL works end-to-end.

---

### Task 1: Schemas + State
> Define the data model before writing any agent logic.

- [ ] **1a.** `schemas/health.py` — `HealthProfile` model:
  ```python
  class HealthProfile(BaseModel):
      age: int
      weight_lbs: float
      sex: Literal["female", "male", "other"]
      health_goals: list[str]           # "better sleep", "muscle recovery"
      current_supplements: list[str]
      medications: list[str]
      conditions: list[str]             # "pregnant", "thyroid", etc.
      allergies: list[str]
      monthly_budget: float
  ```
- [ ] **1b.** `schemas/product.py` — `ShopifyProduct`, `ProductComparison`, `IngredientAnalysis`
- [ ] **1c.** `schemas/recommendation.py` — `SupplementStack`, `StackItem`, `StoreCart`
- [ ] **1d.** `schemas/run.py` — `SupplementStateSnapshot`, phase types (`"memory" | "discovery" | "analysis" | "checkout"`), `SupplementRunEvent`
- [ ] **1e.** `events.py` — supplement-local event emitter helpers (`emit_supplement_event`, `bind_event_emitter`) wired to `SupplementRunEvent`
- [ ] **1f.** `agents/state.py` — `SupplementRunState` TypedDict + subgraph states

---

### Task 2: Agent Nodes
> Each node is a standalone async function. Test in isolation before wiring into graph.

- [ ] **2a.** `health_goal_analyzer.py` — LLM takes HealthProfile → returns list of supplement categories needed (e.g., "magnesium for sleep", "creatine for recovery") with search queries per category
- [ ] **2b.** `store_searcher.py` — Takes categories + search queries → parallel MCP `search_store` calls across verified stores → returns `dict[category, dict[store, list[ShopifyProduct]]]`
- [ ] **2c.** `ingredient_comparator.py` — LLM takes products per category → compares ingredients, dosages, bioavailability, price per serving → returns `list[ProductComparison]` with ranked options
- [ ] **2d.** `stack_builder.py` — LLM takes all comparisons + health profile + budget → builds optimal `SupplementStack` considering interactions, total cost, user constraints
- [ ] **2e.** `supplement_critic.py` — Three-concern critic:
  - **Safety:** allergens, excessive dosages, medication interactions → if medications/conditions present and risk unclear, return `"manual_review_needed"`
  - **Goal alignment:** does the stack address stated goals?
  - **Value:** cost-effective? within budget?
- [ ] **2f.** `mcp_cart_builder.py` — Takes the recommended stack, creates carts before approval, calls `update_cart` per store, returns `list[StoreCart]` with checkout URLs

---

### Task 3: Subgraphs + Graph
> Wire nodes into LangGraph subgraphs, then compose into the main graph.

- [ ] **3a.** `subgraphs/discovery.py` — `health_goal_analyzer → store_searcher`
- [ ] **3b.** `subgraphs/analysis.py` — `ingredient_comparator → stack_builder`
- [ ] **3c.** `subgraphs/critic.py` — `supplement_critic` (single node subgraph, but keeps the pattern consistent)
- [ ] **3d.** `subgraphs/checkout.py` — `mcp_cart_builder` builds carts, persists checkout URLs, emits `approval_requested`, returns without resume logic
- [ ] **3e.** `agents/graph.py` — `build_supplement_graph`:
  ```
  START → supervisor → load_memory → discovery → analysis → critic
                                                              ↓
                                          critic passes → checkout(build carts + await approval) → END
                                          critic fails + retries left → analysis (replan)
                                          critic fails + no retries → END
  ```
- [ ] **3f.** `agents/supervisor.py` — routing logic
- [ ] **3g.** Test full graph end-to-end in terminal with a hardcoded HealthProfile

---

### Task 4: DB Model + API Routes
> Persistence and HTTP endpoints.

- [ ] **4a.** `models/run.py` — `SupplementRun` SQLAlchemy model (dedicated `supplement_runs` table). Columns: `run_id`, `user_id`, `status`, `state_snapshot` (JSON), `created_at`, `updated_at`
- [ ] **4b.** Alembic migration (or auto-create for demo)
  - If using auto-create, ensure `SupplementRun` is imported into the shared SQLAlchemy `Base` metadata before app startup so `create_all()` actually creates `supplement_runs`
- [ ] **4c.** `SupplementRunManager` — owns the supplement graph, handles event emission, persists snapshots
- [ ] **4d.** `api/routes.py`:
  - `POST /v1/supplements/runs` — create + start a supplement run (accepts HealthProfile)
  - `GET /v1/supplements/runs/{run_id}` — get run state
  - `GET /v1/supplements/runs/{run_id}/stream` — SSE events
  - `POST /v1/supplements/runs/{run_id}/approve` — record approved stores, mark complete, return the existing checkout URLs
- [ ] **4e.** Wire routes into `main.py` app (add supplement router alongside existing grocery router)
- [ ] **4f.** Test API end-to-end with curl/httpie

---

### Task 5: Frontend
> New route group + components. Shameless duplication from grocery UI.

- [ ] **5a.** `web/src/lib/supplement-types.ts` — TypeScript types mirroring supplement schemas
- [ ] **5b.** `web/src/hooks/use-supplement-run.ts` — React Query hooks for supplement API
- [ ] **5c.** `web/src/app/supplements/page.tsx` — Health profile intake form + "Find My Stack" button
- [ ] **5d.** `web/src/components/supplements/health-form.tsx` — Form component (goals, conditions, meds, budget)
- [ ] **5e.** `web/src/components/supplements/product-comparison.tsx` — Side-by-side product cards per category
- [ ] **5f.** `web/src/components/supplements/stack-recommendation.tsx` — Final recommended stack with total cost
- [ ] **5g.** `web/src/components/supplements/checkout-links.tsx` — Per-store checkout URL buttons + approval
- [ ] **5h.** `web/src/app/supplements/[runId]/page.tsx` — Run detail page:
  - RunProgress (adapted for supplement phases)
  - Discovery results → comparison cards → recommendation → approval → checkout links
- [ ] **5i.** Add supplements nav link to `web/src/components/layout/nav.tsx`

---

### Task 6: Demo Polish
> Only after Tasks 0-5 are working.

- [ ] **6a.** End-to-end happy path test: form → run → stream → comparison → approve → checkout URLs open with items in cart
- [ ] **6b.** Error handling: what if a store MCP call fails mid-run? Graceful degradation (skip that store, continue with others)
- [ ] **6c.** Record backup demo video in case of network issues during pitch
- [ ] **6d.** Rehearse the demo flow and pitch narrative

---

## Cut List (Skip for 48h Demo)

- Evals — add after demo
- Memory integration — hardcode health profile from form, skip episodic memory loading
- Critic replan loop — run critic once, don't loop (set `MAX_REPLANS = 0`)
- Browser automation fallback — just show checkout URLs
- Catalog MCP (cross-store global search) — requires auth setup, use per-store Storefront MCP instead
- Audit log persistence — skip, just stream events
- User accounts / profile persistence — health profile comes from the form each time
- ContextAssembler reuse — keep supplement prompting local

---

## Schedule

| Block | Hours | Task | Exit Criteria |
|---|---|---|---|
| Day 1 AM | 0-3 | **Task 0: MCP Spike** | Working MCP client, 2-3 verified stores |
| Day 1 AM | 3-5 | **Task 1: Schemas + State** | All types defined, state compiles |
| Day 1 PM | 5-9 | **Task 2: Agent Nodes** | Each node tested in isolation with real MCP data |
| Day 1 PM | 9-12 | **Task 3: Graph** | Full graph runs end-to-end in terminal |
| Day 2 AM | 12-16 | **Task 4: API** | curl can create run, stream events, approve, get checkout URLs |
| Day 2 AM | 16-20 | **Task 5: Frontend** | UI shows full flow from form to checkout links |
| Day 2 PM | 20-24 | **Task 6: Polish** | Demo rehearsed, backup video recorded |
| Buffer | 24-48 | **Overflow** | Fix bugs, pitch deck, sleep |

---

## Demo Script

```
User fills health form:
  "28M, 180lbs. Goals: better sleep, muscle recovery.
   No medications. No conditions. Allergies: none. Budget: $80/mo"

[Discovery] Analyzing health goals...
  → Need: magnesium (sleep), creatine (recovery), possibly vitamin D
  → Searching Ritual... Transparent Labs... Momentous...
  → Found 12 products across 3 stores

[Analysis] Comparing products...
  → Magnesium: Momentous L-Threonate ($34.95) vs Ritual Essential ($33/mo)
  → Creatine: Transparent Labs Creatine HMB ($49.99) vs Momentous Creatine ($29.95)
  → Side-by-side comparison cards with ingredients, dosages, price/serving

[Critic] Checking safety and goal alignment...
  → No allergens detected ✓
  → Addresses both stated goals ✓
  → Total $64.90/mo — within $80 budget ✓

[Recommendation] Your personalized stack:
  1. Momentous Magnesium L-Threonate — $34.95 (sleep)
  2. Momentous Creatine — $29.95 (recovery)
  Total: $64.90/mo

[Checkout] Ready to purchase from 1 store.
  → [Approve & Checkout]  [Modify Stack]

User clicks Approve → checkout URL opens Momentous with both items in cart.
```
