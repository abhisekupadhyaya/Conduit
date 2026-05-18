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
from typing import Literal

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
    fulfilment_mode: Literal["dispatch", "no_dispatch"] | None
    outcome: Literal["auto", "clarify", "flag", "no_dispatch"]
    is_problem_report: bool
    requested_checkout: str | None = None


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
    "Decompose the guest message into independent children. For each child, "
    "set issue_code to exactly one code from the injected CATALOG (active "
    "only) whose meaning matches, or null if none matches. Set "
    "fulfilment_mode to the matched code's mode (null if no code). "
    "Set is_problem_report true only on objective broken/not-working "
    "framing (not tone). Set outcome by these rules, in order: "
    "(1) money/safety/guest-move/reservation-change risk => 'flag'; "
    "(2) no code matched, or the request is too vague to act on => "
    "'clarify'; (3) matched code fulfilment_mode == 'no_dispatch' => "
    "'no_dispatch'; (4) matched code fulfilment_mode == 'dispatch' => "
    "'auto'. CASUAL-CONVERSATION PRECEDENCE: if a casual-conversation "
    "code is in CATALOG, match it for ANY social, meta, or non-service "
    "message even when phrased as a question or a request to know "
    "something - greetings, thanks, banter, 'how are you', 'what is "
    "your name', 'what can you do', jokes, opinions, and general / "
    "off-topic / world-knowledge questions not about THIS hotel or the "
    "guest's own stay. Use INFO_* / service codes ONLY for questions "
    "about this hotel or this guest's stay (hours, wifi, amenities, "
    "housekeeping, the reservation). When in doubt between a casual code "
    "and an INFO_* code for a non-hotel topic, choose the casual code "
    "(then rule 3 applies: outcome 'no_dispatch'). "
    "outcome MUST be exactly one of: auto, clarify, flag, "
    "no_dispatch. Never drop a need; never omit a child."
    " If a child matches a reservation-mutation code and the guest is "
    "asking to change their checkout time/date, set requested_checkout to "
    "the requested checkout as an ISO-8601 timestamp resolved against the "
    "conversation; otherwise leave requested_checkout null."
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


class _Smalltalk(BaseModel):
    reply: str


_SYS_SMALLTALK = (
    "You are the hotel's friendly stay assistant. The guest sent a "
    "casual, social, meta, or off-topic message. Hold up the small talk "
    "naturally: reply in one or two short, warm, human sentences. You MAY "
    "banter lightly, react, and answer harmless questions about yourself "
    "(you're the hotel's assistant, here to help with their stay). For "
    "anything outside this hotel or their stay (world facts, places, "
    "trivia, advice, opinions) do NOT pretend to know or give an "
    "authoritative answer - good-naturedly acknowledge it's outside what "
    "you can help with and steer back to their stay. State NO hotel facts "
    "(hours, prices, names, policies, room details) and make NO promises "
    "or bookings. Always sound like a warm human, never a form."
)


@retry(
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _parse_smalltalk(model: str, message: str) -> _Smalltalk:
    r = await _client().responses.parse(
        model=model,
        input=[{"role": "system", "content": _SYS_SMALLTALK},
               {"role": "user", "content": message}],
        text_format=_Smalltalk, reasoning={"effort": "low"})
    return r.output_parsed


async def classify(text: str, catalog: list[dict],
                   history: str = "") -> list[dict]:
    s = get_settings()
    if _circuit_open():
        raise LLMUnavailable("circuit open")
    cat = "\n".join(
        f"{c['code']} | {c['label']} | {c['fulfilment_mode']} | "
        f"mutation={c['is_reservation_mutation']}" for c in catalog)
    model = s.openai_model
    user = (f"CONVERSATION (oldest→newest, context only):\n{history}\n\n"
            f"CURRENT MESSAGE:\n{text}") if history else text
    try:
        parsed = await _parse_classify(
            model, _SYS_CLASSIFY + "\nCATALOG:\n" + cat, user)
    except Exception as e:  # timeout / circuit / api error
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return [c.model_dump() for c in parsed.children]


async def ground(question: str, context: str, history: str = "") -> dict:
    s = get_settings()
    if _circuit_open():
        raise LLMUnavailable("circuit open")
    model = s.openai_model
    q = (f"CONVERSATION (context only):\n{history}\n\nQUESTION: {question}"
         if history else f"QUESTION: {question}")
    try:
        parsed = await _parse_ground(
            model, f"{q}\n\nCONTEXT\n{context}")
    except Exception as e:
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return parsed.model_dump()


async def smalltalk(message: str) -> str:
    s = get_settings()
    if _circuit_open():
        raise LLMUnavailable("circuit open")
    try:
        parsed = await _parse_smalltalk(s.openai_model, message)
    except Exception as e:
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return parsed.reply
