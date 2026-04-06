# Shopper

The current repo implements the upstream planning workflow for the AI meal planner and grocery shopping agent.

Today’s backend architecture is:

- FastAPI app with run-centric `POST /v1/runs` and `GET /v1/runs/{run_id}`
- LangGraph flow with `supervisor -> load_memory -> planning_subgraph -> planning_critic_subgraph -> end`
- unified upstream planning subgraph: `nutrition_planner -> meal_selector -> grocery_builder -> price_optimizer`
- one bounded repair loop driven by the `critic`
- deterministic validation for nutrition, safety, grocery traceability, purchase-order coverage, and budget fit
- memory/context scaffolding with LangSmith-friendly context metadata and evaluation harnesses

The app runs fully offline by default. Local runs still get a local trace ID,
and remote LangSmith tracing turns on when `LANGSMITH_TRACING`,
`LANGSMITH_PROJECT`, and `LANGSMITH_API_KEY` are set. When enabled, planner
invocations use LangSmith's tracing context so LangGraph can emit nested
node/tool/LLM spans instead of a single manually posted top-level run. Legacy
`LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, and `LANGCHAIN_API_KEY` env vars
are also accepted.
