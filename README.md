# Shopper

This repository now includes the Phase 5 browser checkout path on top of the
existing planning and shopping flows.

Current backend highlights:

- run-centric FastAPI API for planning, shopping, checkout creation, and checkout resume
- LangGraph orchestration for planning, shopping, and a checkout subgraph
- deterministic cart verification and spending guardrails before purchase
- human approval flow with `awaiting_approval` run state and `/v1/runs/{id}/resume`
- audit log and purchase-order persistence
- standalone browser checkout runner in [`scripts/run_checkout_agent.py`](/Users/michaelzhu/Desktop/shopper/scripts/run_checkout_agent.py)

## Checkout setup

The base project still runs in the checked-in Python 3.9 environment for the
existing planner tests, but live browser checkout uses `browser-use`, which
requires Python 3.11+.

Recommended setup for live checkout:

```bash
uv venv .venv311 --python 3.11
uv pip install --python .venv311/bin/python -e '.[dev,checkout]'
./.venv311/bin/playwright install chromium
cp .env.example .env
```

For browser checkout you can use the existing `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`. `BROWSER_USE_API_KEY` is optional and is only needed if you
want the Browser Use hosted model or cloud browser.

Authentication for real grocery sites will usually require one of these:

- `SHOPPER_BROWSER_CHECKOUT_STORAGE_STATE_PATH` pointing to a Playwright storage-state JSON
- `SHOPPER_BROWSER_CHECKOUT_USER_DATA_DIR` pointing to a logged-in browser profile

### Browser Use Cloud

For the most reliable Browser Use setup, enable the managed cloud browser:

```bash
SHOPPER_BROWSER_CHECKOUT_USE_CLOUD=true
SHOPPER_BROWSER_CHECKOUT_CLOUD_PROFILE_ID=your-profile-id
SHOPPER_BROWSER_CHECKOUT_CLOUD_PROXY_COUNTRY_CODE=us
SHOPPER_BROWSER_CHECKOUT_CLOUD_TIMEOUT_MINUTES=15
SHOPPER_BROWSER_CHECKOUT_CAPTCHA_SOLVER=true
```

`SHOPPER_BROWSER_CHECKOUT_CLOUD_TIMEOUT_MINUTES` maps directly to Browser Use's
cloud session timeout in minutes. Free Browser Use plans are capped at 15
minutes; paid plans can go higher.

To smoke-test the cloud browser before trying a store run:

```bash
PYTHONPATH=src ./.venv311/bin/python scripts/check_browser_cloud.py --url "https://example.com"
```

That script opens a Browser Use cloud browser with the current `.env` settings
and prints the page title and resolved URL.

## Standalone checkout runner

The checkout agent is independently runnable:

```bash
PYTHONPATH=src ./.venv311/bin/python scripts/run_checkout_agent.py \
  --items /path/to/items.json \
  --store "Demo Store" \
  --start-url "https://example.com"
```

Add `--approve` only when you want it to finish the actual checkout after cart
preparation.
