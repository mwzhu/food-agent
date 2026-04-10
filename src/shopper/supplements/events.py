from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional
from uuid import uuid4

from shopper.supplements.schemas.run import (
    SupplementPhaseName,
    SupplementRunEvent,
    SupplementRunEventType,
)


SupplementEventEmitter = Callable[[SupplementRunEvent], Awaitable[None]]

_current_event_emitter: ContextVar[Optional[SupplementEventEmitter]] = ContextVar(
    "shopper_current_supplement_event_emitter",
    default=None,
)


@contextmanager
def bind_event_emitter(emitter: SupplementEventEmitter) -> Iterator[None]:
    token = _current_event_emitter.set(emitter)
    try:
        yield
    finally:
        _current_event_emitter.reset(token)


async def emit_supplement_event(
    run_id: str,
    event_type: SupplementRunEventType,
    message: str,
    phase: Optional[SupplementPhaseName] = None,
    node_name: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    emitter = _current_event_emitter.get()
    if emitter is None:
        return

    await emitter(
        SupplementRunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type=event_type,
            message=message,
            phase=phase,
            node_name=node_name,
            data=data or {},
        )
    )
