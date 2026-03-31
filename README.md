# Shopper

Backend-first bounded-autonomy meal planner and grocery agent.

This scaffold implements:

- a run-centric FastAPI API
- LangGraph-backed orchestration for planning and shopping
- deterministic nutrition, grocery, pricing, and verification services
- a memory/context subsystem with canonical facts plus episodic memory
- approval-gated mock browser execution for Walmart

The browser and retrieval integrations are mocked by default so the core
architecture is runnable without external credentials.

# food-agent
