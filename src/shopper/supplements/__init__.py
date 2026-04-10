"""Supplement shopping modules."""

from shopper.supplements.events import bind_event_emitter, emit_supplement_event

__all__ = [
    "bind_event_emitter",
    "emit_supplement_event",
]
