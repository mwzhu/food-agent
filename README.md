# Shopper

Phase 1 of the AI meal planner and grocery shopping agent is implemented here.

This repository now matches the Phase 1 plan in `PLAN.md`:

- FastAPI app with run-centric `POST /v1/runs` and `GET /v1/runs/{run_id}`
- packaged SQLAlchemy models and Pydantic schemas
- LangGraph planning flow with `supervisor -> planning_subgraph -> end`
- deterministic nutrition math plus a prompt-driven Phase 1 meal-selector stub
- memory/context scaffolding with LangSmith-friendly context metadata
- initial nutrition evaluation harness and CLI

The app runs fully offline by default. Local runs still get a local trace ID,
and remote LangSmith tracing turns on when `LANGSMITH_TRACING`,
`LANGSMITH_PROJECT`, and `LANGSMITH_API_KEY` are set. When enabled, planner
invocations use LangSmith's tracing context so LangGraph can emit nested
node/tool/LLM spans instead of a single manually posted top-level run. Legacy
`LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, and `LANGCHAIN_API_KEY` env vars
are also accepted.
