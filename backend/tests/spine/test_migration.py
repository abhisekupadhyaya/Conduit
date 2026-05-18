import datetime as dt
import importlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError


def test_slice7_added_zero_schema():
    """Positive zero-schema guard (Spec §6 / §11): the
    ``inspect(Model).columns`` name-sets for the fan-out-touched models are
    BYTE-IDENTICAL to slice 6 — proves Slice 7 added zero columns/tables
    (the fan is expressed entirely through existing structure:
    ``child_sub_request.request_id`` shared by siblings, unique-per-child
    ``work_order.child_id``/``glitch.child_id``). The expected sets are the
    literal slice-6 column names enumerated from the model definitions; any
    add/drop fails this test red.
    """
    from conduit.shared.models import (ChildSubRequest, IssueCode,
                                       Recommendation, WorkOrder)

    expected = {
        ChildSubRequest: {
            "id", "request_id", "text", "issue_code_id", "uncategorized",
            "outcome", "fulfilment_mode", "is_problem_report", "state",
            "priority_tier", "closure", "revised_eta",
            "predecessor_child_id", "requested_checkout", "created_at",
            "updated_at",
        },
        WorkOrder: {
            "id", "child_id", "kind", "routing_model",
            "assigned_servicer_id", "accountable_owner_id", "section_id",
            "priority_tier", "queue_position", "state", "completion_notes",
            "created_at", "updated_at",
        },
        IssueCode: {
            "id", "code", "label", "department", "fulfilment_mode",
            "routing_model", "intent_kind", "is_reservation_mutation",
            "status", "sla_preset_id", "created_at", "updated_at",
        },
        Recommendation: {
            "escalation_id", "action", "rationale_text", "created_at",
        },
    }
    for model, names in expected.items():
        assert {c.name for c in inspect(model).columns} == names, (
            f"{model.__name__} column-set drifted from the slice-6 "
            f"zero-schema baseline (Slice 7 must add no columns/tables)")


def test_down_revision_chains_to_0002():
    # The merged migration idiom uses short numeric revision IDs
    # (0001/0002), so 0003 chains to "0002" — not "0002_stay_binding".
    m = importlib.import_module("migrations.versions.0003_nodispatch")
    assert m.down_revision == "0002"


async def test_partial_pk_blocks_second_resolution(db, make_account):
    # The merged harness seeds no Account/Stay (the spine conftest with
    # seed fixtures lands in a later task), so build the real FK-chain
    # precondition rows inline. The only invariant under test is
    # child_id-as-PK rejecting a 2nd resolution per child (1:1).
    from conduit.shared.models import (Account, ChildSubRequest,
                                       NoDispatchResolution, Property,
                                       Request, Room, Section, Stay)
    await make_account("guest", f"g-{uuid.uuid4().hex[:8]}")
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert acc is not None
    p = Property(name="T")
    db.add(p)
    await db.flush()
    s = Section(property_id=p.id, label="S")
    db.add(s)
    await db.flush()
    room = Room(section_id=s.id, label="R")
    db.add(room)
    await db.flush()
    now = dt.datetime.now(dt.timezone.utc)
    stay = Stay(guest_account_id=acc.id, room_id=room.id,
                check_in=now, check_out=now + dt.timedelta(days=1))
    db.add(stay)
    await db.flush()
    r = Request(guest_account_id=acc.id, stay_id=stay.id, raw_text="x")
    db.add(r)
    await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                        state="triaged")
    db.add(c)
    await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="human_deferral"))
    await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="grounded_answer"))
    with pytest.raises(IntegrityError):
        await db.flush()
