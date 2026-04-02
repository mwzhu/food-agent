from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional
from uuid import uuid4

from shopper.schemas import PhaseName, RunEvent, RunEventType


EventEmitter = Callable[[RunEvent], Awaitable[None]]

_current_event_emitter: ContextVar[Optional[EventEmitter]] = ContextVar(
    "shopper_current_event_emitter",
    default=None,
)


@contextmanager
def bind_event_emitter(emitter: EventEmitter) -> Iterator[None]:
    token = _current_event_emitter.set(emitter)
    try:
        yield
    finally:
        _current_event_emitter.reset(token)


async def emit_run_event(
    run_id: str,
    event_type: RunEventType,
    message: str,
    phase: Optional[PhaseName] = None,
    node_name: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    emitter = _current_event_emitter.get()
    if emitter is None:
        return

    await emitter(
        RunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type=event_type,
            message=message,
            phase=phase,
            node_name=node_name,
            data=data or {},
        )
    )
