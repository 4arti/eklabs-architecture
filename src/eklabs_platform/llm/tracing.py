"""Langfuse Cloud wiring, kept separate from claude_client.py so Phase 3's
real drafting agent (which will need multi-step traces, not just one call)
doesn't have to touch tracing plumbing to get it — it already has it.
"""

from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from langfuse import observe

P = ParamSpec("P")
R = TypeVar("R")


def traced(*, name: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Thin wrapper around Langfuse's `@observe()` so call sites (e.g.
    claude_client.complete()) name the thing being traced without every
    caller needing to know Langfuse's own decorator signature."""

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        return observe(name=name)(fn)

    return decorator
