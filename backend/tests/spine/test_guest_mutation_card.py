"""Task 14 — Guest read model surfaces the reservation_mutation outcome.

The ``confirm`` endpoint already works for ``state=='answered'`` + any
resolution; only the READ (``list_conversation``) needed to also recognise
``reservation_mutation`` mode so the card shows answer text + closure prompt
(it previously special-cased ``grounded_answer`` only).

``list_conversation`` is the guest *conversation* read projection. The
dispatch router composes its ``GET /requests`` FIRST and shadows the
conversation router's ``GET /requests`` (see ``conduit/guest/api/__init__.py``
and the explicit note in ``test_structural_guards.py``: "The dispatch router
owns GET /requests (DispatchCardOut)"). The conversation read is therefore
exercised by invoking the real ``list_conversation`` view function directly
on the savepoint-isolated session with a real guest ``Actor`` — exactly the
proven "drive the real service/view directly on ``db``" pattern used across
the spine package (e.g. ``test_e2e_journey`` calling
``intake.submit_request(db, actor, ...)``).

Seeding reuses the proven ``conftest.py`` / ``test_guest_dal.py`` patterns
verbatim: ``make_account`` builds the guest via the real account service (the
conftest default password ``"pw-123456"``), then the
Property→Section→Room→Stay→Request→ChildSubRequest FK chain is flushed exactly
as ``seeded_guest_with_stay`` / ``make_child`` build it.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from conduit.core.deps import Actor
from conduit.guest.api.conversation import list_conversation
from conduit.shared.models import (
    ChildSubRequest,
    NoDispatchResolution,
    Property,
    Request,
    Room,
    Section,
    Stay,
)

_PW = "pw-123456"  # conftest default in make_account / login


@pytest.mark.asyncio
async def test_mutation_resolution_renders_answer_and_closure(db,
                                                              make_account):
    """A child in state 'answered' with a reservation_mutation resolution
    surfaces answer_text + closure_prompt via the guest conversation read."""
    # Seed (reuse conftest/test_guest_dal.py patterns): a guest + active stay
    # + a child(state='answered') + NoDispatchResolution(
    # mode='reservation_mutation', answer_text='Your checkout is now ...').
    acc = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    p = Property(name="T")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label="S")
    db.add(sec)
    await db.flush()
    room = Room(section_id=sec.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1),
                status="active")
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    child = ChildSubRequest(request_id=r.id, text="move my checkout",
                            outcome="no_dispatch", state="answered")
    db.add(child)
    await db.flush()
    answer = "Your checkout is now 2026-05-20 14:00."
    db.add(NoDispatchResolution(child_id=child.id,
                                mode="reservation_mutation",
                                answer_text=answer))
    await db.flush()

    # Drive the REAL conversation read directly on the savepoint session as
    # this guest (Actor.id is a str — current_actor builds it from the token
    # 'sub'; the DAL compares it against Request.guest_account_id).
    actor = Actor(id=str(acc.id), role="guest")
    out = await list_conversation(actor=actor, s=db)

    req = next(o for o in out if o.request_id == str(r.id))
    child_out = next(c for c in req.children
                     if c.child_id == str(child.id))

    # The mutation outcome renders identically to a grounded_answer:
    # answer text surfaced AND the closure prompt true.
    assert child_out.answer == answer
    assert child_out.closure_prompt is True
    assert child_out.terminal == "answered"
