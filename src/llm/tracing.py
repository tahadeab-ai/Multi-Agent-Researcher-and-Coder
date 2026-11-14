"""No-op tracing hook for Phase 1.

A minimal Span/Tracer abstraction is wired here so Phase 4 can
activate real OTel/Langfuse tracing by swapping the implementation
without touching call sites. The environment variable
PHOENIX_TRACER_ENABLED=langfuse will activate the real integration
when Phase 4 wires it.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """A tracing span (no-op implementation for Phase 1)."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN401
        self.attributes[key] = value

    def end(self) -> None:
        pass


class _NoOpTracer:
    """No-op tracer that discards all spans."""

    @contextmanager
    def span(self, name: str) -> Generator[Span, None, None]:
        s = Span(name=name)
        try:
            yield s
        finally:
            s.end()


def get_tracer() -> _NoOpTracer:
    """Return the active tracer.

    Phase 4 will check PHOENIX_TRACER_ENABLED and return a real tracer.
    """
    enabled = os.environ.get("PHOENIX_TRACER_ENABLED", "").lower()
    if enabled == "langfuse":
        # Phase 4 will implement this branch.
        # For now, fall through to no-op so the env var is acknowledged.
        pass
    return _NoOpTracer()
