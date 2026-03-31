# Shopper

Phase 1 of the AI meal planner and grocery shopping agent is implemented here.

This repository now matches the Phase 1 plan in `PLAN.md`:

- FastAPI app with run-centric `POST /v1/runs` and `GET /v1/runs/{run_id}`
- packaged SQLAlchemy models and Pydantic schemas
- LangGraph planning flow with `supervisor -> planning_subgraph -> end`
- deterministic nutrition math plus a prompt-driven Phase 1 meal-selector stub
- memory/context scaffolding with LangSmith-friendly context metadata
- initial nutrition evaluation harness and CLI

The app runs fully offline by default. LangSmith tracing works in local mode
through local trace IDs, and remote LangSmith logging/experiments turn on only
when `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, and `LANGSMITH_API_KEY` are set.
