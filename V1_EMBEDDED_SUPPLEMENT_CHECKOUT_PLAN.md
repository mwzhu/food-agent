# V1 Embedded Supplement Checkout Plan

## Goal

Turn `/v1` into the primary supplement buying product where:

1. the user asks for a supplement stack in `/v1`
2. the agent discovers and compares products
3. the user approves one or more stores
4. checkout and payment stay inside our app shell whenever Shopify allows it
5. the agent completes merchant-scoped purchases and returns confirmations back into the same conversation

This replaces the current `/v1` behavior, where the buy action ends with a checkout URL opened in a new tab.

## Current State In This Repo

### Frontend

- `/v1` already exists in [web/src/app/v1/page.tsx](/Users/michaelzhu/Desktop/shopper/web/src/app/v1/page.tsx)
- the full supplement experience currently lives in [web/src/components/v1/v1-workspace.tsx](/Users/michaelzhu/Desktop/shopper/web/src/components/v1/v1-workspace.tsx)
- the current `handleBuy` path still opens `checkoutUrl` in a new tab

### Supplement backend

- supplement runs are created/read/approved in [src/shopper/supplements/api/routes.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/api/routes.py)
- approval currently marks the run complete in [src/shopper/supplements/services/run_manager.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/services/run_manager.py)
- supplement checkout currently stops at carts plus checkout URLs in [src/shopper/supplements/agents/nodes/mcp_cart_builder.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/agents/nodes/mcp_cart_builder.py)

### Existing infrastructure we can reuse

- DB/bootstrap already exist in [src/shopper/db.py](/Users/michaelzhu/Desktop/shopper/src/shopper/db.py)
- supplement persistence already exists in [src/shopper/supplements/models/run.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/models/run.py)
- browser/profile sync and checkout artifact patterns already exist in [src/shopper/api/routes/checkout_profiles.py](/Users/michaelzhu/Desktop/shopper/src/shopper/api/routes/checkout_profiles.py) and [src/shopper/agents/tools/browser_tools.py](/Users/michaelzhu/Desktop/shopper/src/shopper/agents/tools/browser_tools.py)

This is important: we are not standing up persistence from scratch. We are adding supplement-specific tables and state to an existing backend.

## Product Boundary

### What "buy inside my app" means

- preferred path: embedded Shopify checkout continuation inside `/v1`
- acceptable path: embedded `continue_url` / Checkout Kit / ECP-style flow inside the app shell
- last-resort fallback: open a merchant checkout in a new tab only when embedding is impossible

### What it does not mean

- not one universal cross-store cart
- not one single payment across multiple merchants
- not guaranteed silent no-confirmation payment on every merchant

Multi-store purchases will still be one merchant checkout per store, but the user experience should feel like one guided in-app flow.

## Execution Principles

1. `/v1` is the first-class surface. New work should target `/v1`, not the legacy `/supplements` pages.
2. Spike first. The embedded checkout bet must be validated before we build the full orchestration layer.
3. Keep the frontend simple. The UI should expose only the states users care about.
4. Separate MVP from Phase 2. One-store in-app checkout is the immediate goal. Multi-store and deeper payment automation come later.
5. Keep graceful fallback. If embedding fails, the experience should degrade intentionally instead of stalling.

## User-Facing State Model

The frontend should expose only four top-level states:

- `planning`
- `awaiting_approval`
- `checkout_in_progress`
- `completed_or_needs_attention`

The backend can keep richer internal substates, but `/v1` should not leak them directly.

### Internal checkout substates

These remain backend-only and can be collapsed in UI:

- buyer profile missing
- preparing checkout session
- awaiting payment handler selection
- awaiting buyer confirmation
- merchant escalation required
- completing order
- order placed
- payment failed
- checkout failed

## Phase 0: Feasibility Spike

This is the new blocking phase. Do not commit to the full build until this passes.

### Objective

Prove whether a supported Shopify supplement merchant can be driven inside our app shell without relying on a normal external browser tab.

### Scope

Test one known-good merchant from our current set:

- `transparentlabs.com` or `livemomentous.com`

Test all of the following:

1. authenticated Checkout MCP session creation
2. actual continuation data returned by the merchant
3. whether the merchant flow can be presented inside our app shell
4. whether normal iframe embedding is blocked by CSP / X-Frame-Options
5. whether a Checkout Kit / ECP / controlled webview path works better
6. what the fallback looks like when embedding is blocked
7. desktop behavior
8. mobile behavior in a constrained viewport

### Deliverables

- a short spike writeup
- one proof-of-concept route or dev page
- screenshots or recordings for desktop and mobile
- explicit result for each rendering mode:
  - iframe
  - embedded webview style surface
  - `continue_url` fallback

### Exit criteria

One of these must be true:

1. we prove one merchant can complete a viable in-app flow inside `/v1`
2. we prove embedding is blocked often enough that the product should pivot to an agent-narrated controlled handoff instead

If the spike fails, the project should pivot before building the full orchestrator.

## Architecture After The Spike

### Discovery and recommendation

- keep the current supplement run graph for intake, discovery, comparison, stack building, and critic review
- later upgrade discovery toward authenticated Catalog MCP for production breadth

### Checkout orchestration

- after store approval, create one Checkout MCP session per approved store
- attach buyer and shipping data
- inspect `payment.handlers`
- if `dev.shopify.shop_pay` is supported, start the delegated Shop Pay flow
- present buyer confirmation inside the app shell when possible
- call `complete_checkout`
- persist order confirmations back onto the supplement run

### Fallback hierarchy

1. embedded checkout inside `/v1`
2. embedded `continue_url` inside `/v1`
3. controlled new-tab handoff with strong agent narration

## Backend Implementation Plan

### Phase 1: Shopify auth and local development setup

Add new settings in [src/shopper/config.py](/Users/michaelzhu/Desktop/shopper/src/shopper/config.py):

- `SHOPIFY_MCP_CLIENT_ID`
- `SHOPIFY_MCP_CLIENT_SECRET`
- `SHOPIFY_MCP_TOKEN_REFRESH_SKEW_S`
- `SHOPIFY_UCP_PROFILE_URL`
- `SHOPIFY_SHOP_PAY_CLIENT_ID`
- `SHOPIFY_MCP_ENABLED`
- `SHOPIFY_CHECKOUT_EMBED_MODE`

Add:

- `src/shopper/supplements/services/shopify_agent_auth.py`

Responsibilities:

- exchange client credentials for the Shopify global bearer token
- cache token with expiry awareness
- expose authenticated headers for Catalog MCP and Checkout MCP

### Phase 2: UCP profile strategy with dev/prod split

Add a `/.well-known/ucp` endpoint eventually, but do not let this block local progress.

Development path:

- allow a stubbed profile URL or tunnel-backed URL
- support local testing before a stable production domain exists

Production path:

- host a real public `/.well-known/ucp`
- use that stable URL in Checkout MCP metadata

### Phase 3: Catalog and Checkout MCP clients

Add:

- `src/shopper/supplements/tools/catalog_mcp.py`
- `src/shopper/supplements/tools/checkout_mcp.py`
- `src/shopper/supplements/tools/shop_pay_handler.py`

`catalog_mcp.py` responsibilities:

- authenticated cross-merchant search
- merchant eligibility metadata
- global product details

`checkout_mcp.py` responsibilities:

- `tools/list`
- `create_checkout`
- `get_checkout`
- `update_checkout`
- `complete_checkout`
- `cancel_checkout`

`shop_pay_handler.py` responsibilities:

- start delegated Shop Pay authorization
- receive and validate Shop Tokens
- normalize handler responses for checkout completion

### Phase 4: Buyer profile and checkout session persistence

Add supplement-local models and schemas:

- `src/shopper/supplements/models/buyer_profile.py`
- `src/shopper/supplements/models/checkout_session.py`
- `src/shopper/supplements/schemas/buyer_profile.py`
- `src/shopper/supplements/schemas/checkout_session.py`

Persist:

- buyer email
- shipping address
- billing country
- consent state
- max per-order cap
- max monthly cap
- Shop Pay linked status
- last payment authorization timestamp

Do not persist:

- raw card numbers
- CVV
- unredacted payment credentials

### Phase 5: Extend supplement run state

Update:

- [src/shopper/supplements/schemas/run.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/schemas/run.py)
- [src/shopper/supplements/services/run_manager.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/services/run_manager.py)

Add snapshot fields for:

- buyer profile readiness
- approved stores
- checkout sessions per merchant
- embedded continuation state
- `continue_url`
- `payment.handlers`
- Shop Pay authorization state
- order confirmations
- fallback reason

### Phase 6: Replace approval-only completion

Current behavior:

- approval marks the supplement run complete immediately

New behavior:

- approval hands off into checkout orchestration
- run completion only happens after merchant orders succeed, fail, or are explicitly skipped

Add endpoints under [src/shopper/supplements/api/routes.py](/Users/michaelzhu/Desktop/shopper/src/shopper/supplements/api/routes.py):

- `POST /v1/supplements/runs/{run_id}/buyer-profile`
- `GET /v1/supplements/runs/{run_id}/buyer-profile`
- `POST /v1/supplements/runs/{run_id}/approve-stores`
- `POST /v1/supplements/runs/{run_id}/checkout/start`
- `POST /v1/supplements/runs/{run_id}/checkout/{store_domain}/continue`
- `POST /v1/supplements/runs/{run_id}/checkout/{store_domain}/cancel`
- `GET /v1/supplements/runs/{run_id}/checkout/{store_domain}`

### Phase 7: Merchant capability cache

Add:

- `src/shopper/supplements/services/merchant_capabilities.py`

Responsibilities:

- cache whether a merchant exposes Checkout MCP
- cache whether a merchant appears to support Shop Pay handler
- flag selling-plan and escalation-heavy merchants

### Phase 8: Embedded checkout orchestrator

Add:

- `src/shopper/supplements/services/embedded_checkout_orchestrator.py`

Responsibilities:

- create merchant checkout sessions sequentially
- apply buyer and shipping data
- detect `requires_escalation`
- produce embedded step metadata for the frontend
- complete orders
- persist confirmations and errors

## Frontend Implementation Plan For `/v1`

### Phase 1: Stop treating checkout as a link

Refactor [web/src/components/v1/v1-workspace.tsx](/Users/michaelzhu/Desktop/shopper/web/src/components/v1/v1-workspace.tsx):

- replace `checkoutUrl`-centric widget logic with `checkoutSession`-centric state
- replace the current fine-grained `buyState` handling with the 4-state UI model
- keep richer detail inside per-store checkout cards, not the top-level conversation state

### Phase 2: Add v1-specific checkout UI components

Add:

- `web/src/components/v1/buyer-profile-drawer.tsx`
- `web/src/components/v1/embedded-checkout-panel.tsx`
- `web/src/components/v1/store-checkout-timeline.tsx`
- `web/src/components/v1/order-confirmation-card.tsx`
- `web/src/components/v1/payment-setup-banner.tsx`

Responsibilities:

- collect buyer setup info
- show store-by-store checkout progress
- host embedded continuation UI
- surface confirmations inline in chat

### Phase 3: Add new hooks and API methods

Update:

- [web/src/lib/api.ts](/Users/michaelzhu/Desktop/shopper/web/src/lib/api.ts)
- [web/src/hooks/use-supplement-run.ts](/Users/michaelzhu/Desktop/shopper/web/src/hooks/use-supplement-run.ts)

Add:

- `web/src/hooks/use-supplement-buyer-profile.ts`
- `web/src/hooks/use-supplement-checkout.ts`

### Phase 4: New `/v1` conversation behavior

The conversation should narrate:

- "I found two stores for this stack."
- "Before I buy, I need your shipping details and payment setup."
- "Transparent Labs is ready for confirmation."
- "Momentous needs an embedded continuation step."
- "Transparent Labs order placed."
- "Momentous order placed."

### Phase 5: Embedded surface strategy

Preferred UI:

- right-side panel on desktop
- full-screen takeover sheet on mobile

This phase depends on the Phase 0 spike result. If the spike shows hard merchant embedding limits, this becomes a controlled continuation surface rather than a true embedded checkout panel.

## Data Model Changes

### Supplement checkout session table

Add one row per merchant checkout attempt with:

- `session_id`
- `run_id`
- `store_domain`
- `checkout_mcp_session_id`
- `status`
- `continue_url`
- `payment_handlers`
- `shop_pay_supported`
- `requires_escalation`
- `embedded_state_payload`
- `order_confirmation_id`
- `order_total`
- `error_code`
- `error_message`

### Buyer payment profile table

Add one row per user with:

- `user_id`
- `email`
- `shipping_name`
- `shipping_address_json`
- `billing_same_as_shipping`
- `autopurchase_enabled`
- `max_order_total`
- `max_monthly_total`
- `shop_pay_linked`
- `shop_pay_last_verified_at`
- `consent_version`

## Testing Strategy

This needs to be explicit because checkout/payment work is where regressions will hide.

### Backend tests

- unit tests for Shopify auth token caching
- unit tests for Checkout MCP response parsing
- unit tests for Shop Pay handler parsing
- state-machine tests for run transitions
- integration tests for buyer profile and checkout session endpoints

### Frontend tests

- component tests for `/v1` checkout state rendering
- tests for buyer profile setup flow
- tests for fallback rendering when embedded checkout is unavailable

### Contract tests

- mocked Checkout MCP fixtures
- mocked `payment.handlers` responses
- mocked `requires_escalation` responses
- mocked success/failure completion payloads

### Real-world verification

- one merchant smoke test for desktop
- one merchant smoke test for mobile
- one fallback smoke test where embedding is blocked

## Manual Steps Required From You

### Shopify setup

1. create a Shopify Dev Dashboard app
2. generate Catalog / MCP credentials
3. register the agent with Shop Pay and obtain the Shop Pay handler `client_id`
4. provide a public HTTPS domain for production
5. confirm the production agent profile URL for `/.well-known/ucp`

For local dev, the production domain should not block the initial spike.

### Merchant rollout

1. pick the first 3 to 5 supplement merchants we will support
2. choose the one-store MVP merchant first
3. decide whether subscription-heavy merchants like Ritual stay out of MVP scope

### Product and policy decisions

1. approve autopurchase consent language
2. choose default user spending caps
3. decide whether Phase 2 multi-store flows run automatically in sequence or require per-store confirmation
4. define refund/support ownership for failed or duplicate orders

### Infrastructure

1. store Shopify secrets in production secret management
2. add migrations for buyer profile and checkout session tables
3. add logging and alerting for payment failures

## Delivery Plan

### Phase 1 MVP

This is the immediate build target.

Includes:

1. Phase 0 embedding spike
2. Shopify auth
3. buyer profile setup in `/v1`
4. one-store checkout session creation
5. one-store in-app continuation flow
6. one-store order confirmation
7. graceful fallback when embedding does not work
8. test coverage for the above

Exit criteria:

- one supported merchant can be purchased through a guided in-app flow in `/v1`
- if true embedding fails, the user still gets a strong agent-led fallback without losing context

### Phase 2 Full Product

Only start this after Phase 1 MVP works.

Includes:

1. Shop Pay handler hardening
2. multi-store sequencing
3. merchant capability cache
4. richer retry/recovery behavior
5. production hardening, analytics, and audit logging

Exit criteria:

- two or more supported merchants can be orchestrated in one guided `/v1` flow
- the system is pilot-ready with clear fallback and support behavior

## Risks

### Shop Pay registration risk

This remains the biggest external dependency. Full autonomous payment will be blocked until this is approved.

### Merchant variability risk

Some merchants will:

- require selling plans
- expose Shop Pay on checkout but still require escalation
- block practical embedding behavior

We should expect a tiered merchant support matrix, not universal parity.

### UX risk

If buyer confirmation is frequent, the UX can still be good, but only if `/v1` frames the process as intentional guided checkout rather than pretending it is fully silent automation.

## Acceptance Criteria

### MVP success

We are done with Phase 1 when:

1. `/v1` no longer depends on `window.open(checkoutUrl)` for the supported MVP merchant
2. the user can stay inside the app shell through the main checkout flow
3. the supplement run remains active through approval, checkout, and confirmation
4. fallback behavior is tested and understandable

### Phase 2 success

We are done with the broader product when:

1. `/v1` supports merchant-by-merchant sequential checkout
2. multiple supported merchants can complete in one guided flow
3. unsupported merchants degrade gracefully
4. buyer setup, confirmations, and audit trails are production-ready

## Recommended First Build Slice

Build in this exact order:

1. Phase 0 spike on one merchant
2. simplify `/v1` to the 4-state model
3. add buyer profile setup
4. build one-store Checkout MCP flow
5. wire embedded or controlled continuation into `/v1`
6. add one-store tests
7. decide whether Phase 2 is worth the added complexity

That keeps the plan honest: validate the hardest bet first, deliver the highest-value portfolio slice second, and only then expand into multi-store autonomy.
