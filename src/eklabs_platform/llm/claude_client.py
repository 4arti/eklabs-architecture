"""The ONLY file in this codebase allowed to import `anthropic`
(CLAUDE.md: "Only `platform/llm/` calls Claude. No AI code anywhere
else."). Every other module that needs a completion calls `complete()`
here — never the Anthropic SDK directly.

Minimal on purpose: nothing in the codebase drafts anything yet (that's
Phase 3's drafter agent). This proves the gateway wiring — auth, a real
call, Langfuse tracing — so Phase 3 has a working door to build on, not a
placeholder.
"""

import functools
import os

from anthropic import AsyncAnthropic

from eklabs_platform.llm.tracing import traced

_DEFAULT_MODEL = "claude-sonnet-5"


@functools.lru_cache(maxsize=1)
def _client() -> AsyncAnthropic:
    # Lazy, not an eager module-level singleton like session.py's engine —
    # ANTHROPIC_API_KEY isn't configured everywhere this module gets
    # imported from, and an eager raise here would break pytest collection
    # for the whole suite the moment it's unset. See storage.py's _client()
    # for the same reasoning.
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Note: a Claude.ai Pro subscription does not "
            "grant API access — generate a key at console.anthropic.com."
        )
    return AsyncAnthropic(api_key=key)


@traced(name="claude.complete")
async def complete(prompt: str, *, model: str = _DEFAULT_MODEL, max_tokens: int = 1024) -> str:
    """One prompt in, one text completion out. No tool calling, no
    streaming yet — the drafter agent (Phase 3) will need both; adding
    them is a widening of this one function's signature, not a new door."""
    response = await _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    block = response.content[0]
    if block.type != "text":
        raise RuntimeError(f"Expected a text content block, got {block.type!r}")
    return block.text
