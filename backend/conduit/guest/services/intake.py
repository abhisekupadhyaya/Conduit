"""Intake orchestration — the guest-side use-case that drives triage.

Triage is not a portal slice (no triage/ api·services·dal·schemas). The
*mechanism* is shared domain (conduit.shared.domain.triage); this service is
just where it is triggered: decompose → per-child classify+triage → echo split
if >1 (D36) → route AUTO / clarify / flag / no-dispatch.
"""
from __future__ import annotations

from conduit.shared.domain import triage


async def submit_request(stay_id: str, raw_text: str) -> list[str]:
    children = triage.decompose(raw_text)  # D35
    # for each: triage.triage(...) → route | clarify | flag | no_dispatch
    raise NotImplementedError
