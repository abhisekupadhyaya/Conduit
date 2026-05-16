"""OpenAI integration — external, bulkheaded (AD11).

Used for decomposition (D35), issue-code classification (D34), and grounded
no-dispatch answers (D26). Wrapped in a timeout + circuit breaker so an LLM
outage degrades into paths the product already defines (flag-to-supervisor /
concierge-deferral, D25) and never stalls the lifecycle.

Privacy: minimise PII in prompts — prefer room/section codes over guest names
where the task allows.
"""
from __future__ import annotations

import threading

from openai import AsyncOpenAI
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from conduit.core.config import get_settings
from conduit.core.exceptions import ConduitError


class LLMUnavailable(ConduitError):
    """Raised when the circuit is open / call times out — callers route into
    the product's degraded paths, never block."""

    status_code = 503


# --- Typed result models (Responses API text_format=) -----------------------

class _Child(BaseModel):
    text: str
    issue_code: str | None
    fulfilment_mode: str | None
    outcome: str
    is_problem_report: bool


class _Decompose(BaseModel):
    children: list[_Child]


class _Ground(BaseModel):
    grounded: bool
    leaves_no_dispatch: bool
    answer: str
    used_kb_ids: list[str]
    used_fields: list[str]


# --- Module-level failure-count circuit breaker -----------------------------
#
# A deliberately tiny bulkhead: count consecutive failures; once it reaches
# _CB_THRESHOLD the circuit is "open" and calls fast-raise LLMUnavailable
# without touching the network. Any success resets the count. Module state so
# a test can trip it directly.

_CB_THRESHOLD = 5
_cb_failures = 0
_cb_lock = threading.Lock()


def _circuit_open() -> bool:
    with _cb_lock:
        return _cb_failures >= _CB_THRESHOLD


def _record_failure() -> None:
    global _cb_failures
    with _cb_lock:
        _cb_failures += 1


def _record_success() -> None:
    global _cb_failures
    with _cb_lock:
        _cb_failures = 0


def _reset_circuit_breaker() -> None:
    global _cb_failures
    with _cb_lock:
        _cb_failures = 0


def _client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(
        timeout=s.openai_timeout_seconds,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
    )


_SYS_CLASSIFY = (
    "Decompose the guest message into independent children; classify each to "
    "exactly one code from the injected CATALOG (active only) or null; "
    "fulfilment_mode from the matched code; is_problem_report only on "
    "objective broken/not-working framing (not tone); risk triggers "
    "(money/safety/moves/reservation change) => flag; never drop a need; "
    "unsure => clarify or flag, never omit."
)
_SYS_GROUND = (
    "Answer ONLY from CONTEXT; insufficient => grounded=false, no answer "
    '(an honest "I\'ll have someone confirm" beats a wrong answer); if '
    "answering requires a reservation/billing/room change => "
    "leaves_no_dispatch=true, grounded=false; on grounded, 1-3 plain "
    "sentences plus the kb_ids/fields used."
)


@retry(
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _parse_classify(model: str, sys: str, text: str) -> _Decompose:
    r = await _client().responses.parse(
        model=model,
        input=[{"role": "system", "content": sys},
               {"role": "user", "content": text}],
        text_format=_Decompose, reasoning={"effort": "low"})
    return r.output_parsed


@retry(
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _parse_ground(model: str, content: str) -> _Ground:
    r = await _client().responses.parse(
        model=model,
        input=[{"role": "system", "content": _SYS_GROUND},
               {"role": "user", "content": content}],
        text_format=_Ground, reasoning={"effort": "low"})
    return r.output_parsed


async def classify(text: str, catalog: list[dict]) -> list[dict]:
    s = get_settings()
    if _circuit_open():
        raise LLMUnavailable("circuit open")
    cat = "\n".join(
        f"{c['code']} | {c['label']} | {c['fulfilment_mode']} | "
        f"mutation={c['is_reservation_mutation']}" for c in catalog)
    model = s.openai_model
    try:
        parsed = await _parse_classify(
            model, _SYS_CLASSIFY + "\nCATALOG:\n" + cat, text)
    except Exception as e:  # timeout / circuit / api error
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return [c.model_dump() for c in parsed.children]


async def ground(question: str, context: str) -> dict:
    s = get_settings()
    if _circuit_open():
        raise LLMUnavailable("circuit open")
    model = s.openai_model
    try:
        parsed = await _parse_ground(
            model, f"QUESTION: {question}\n\nCONTEXT\n{context}")
    except Exception as e:
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return parsed.model_dump()
