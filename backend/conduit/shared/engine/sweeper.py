"""Reconciliation sweeper — the watchdog over the watchdog.

A slower secondary loop that hunts timers that *should* have fired but did
not, and orphaned states, then emits the "age of oldest unfired timer" metric
+ an alarm. This is what justifies running the engine on one cheap instance:
the safety net for "nothing is silently lost" (archi infrastructure §Timers).
"""
from __future__ import annotations


async def sweep() -> None:
    """Detect overdue/orphaned timers and states; emit metric + alarm.

    Implemented alongside the `timer` model. Failed transitions go to a
    failed-transitions record + alarm — never silent.
    """
    raise NotImplementedError
