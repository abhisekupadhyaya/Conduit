"""OpenAI integration — external, bulkheaded (AD11).

Used for decomposition (D35), issue-code classification (D34), and grounded
no-dispatch answers (D26). Wrapped in a timeout + circuit breaker so an LLM
outage degrades into paths the product already defines (flag-to-supervisor /
concierge-deferral, D25) and never stalls the lifecycle.

Privacy: minimise PII in prompts — prefer room/section codes over guest names
where the task allows.
"""
from __future__ import annotations

from conduit.core.config import get_settings
from conduit.core.exceptions import ConduitError


class LLMUnavailable(ConduitError):
    """Raised when the circuit is open / call times out — callers route into
    the product's degraded paths, never block."""

    status_code = 503


async def complete(prompt: str, *, json_mode: bool = True) -> str:
    """Single bounded LLM call. Implemented with httpx + tenacity retry and a
    circuit breaker; on exhaustion raises LLMUnavailable."""
    _ = get_settings()  # endpoint/model/key/timeout
    raise NotImplementedError
