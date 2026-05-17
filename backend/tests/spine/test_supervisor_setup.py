"""Task E5 — Supervisor SLA/ladder CONFIG CRUD (Spec §8 "Supervisor
SLA/ladder CONFIG"; D15 SLA presets, D21 escalation ladder + duty manager).

ONE full-ASGI scripted test driven over the merged per-test ``client`` with
a real per-role cookie chain (``login`` swaps the single active session
cookie — the proven idiom in ``test_issue_codes`` / ``test_staffing_api`` /
``test_supervisor_decisions``).

This mirrors the merged ``issue_code`` CONFIG idiom VERBATIM: POST → 201 +
exactly one append-only event, GET lists, PATCH updates (+ one event) /
disables via ``status`` (NO DELETE → 405), a duplicate ACTIVE row → 409
(the service guard; the partial-unique index is the backstop), incoherent
durations / ``n_cycle_bound`` (≤ 0) → 422, ``extra="forbid"`` → 422,
guest/servicer cookie → 403, no cookie → 401.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from conduit.shared.models import (
    Account,
    EventEscalationLadderCreated,
    EventEscalationLadderUpdated,
    EventSlaPresetCreated,
    EventSlaPresetUpdated,
    Property,
)

_PW = "pw-123456"


async def _seed_property(db) -> uuid.UUID:
    p = Property(name="T")
    db.add(p)
    await db.flush()
    return p.id


async def _duty_manager(make_account) -> Account:
    return await make_account("supervisor", f"dm-{uuid.uuid4().hex[:8]}", _PW)


async def test_supervisor_setup_sla_and_ladder(client, make_account, login, db):
    # Single-property v1 (AD9): the property is resolved server-side, never
    # an operator/body input — so the test seeds exactly ONE property and
    # never passes property_id. Per-property uniqueness at the DB level is
    # covered by the migration/model partial-unique-index test.
    await _seed_property(db)
    duty = await _duty_manager(make_account)
    sup = await make_account("supervisor", f"sup-{uuid.uuid4().hex[:8]}", _PW)
    await db.commit()

    # ===================================================================
    # AUTH MATRIX
    # ===================================================================
    # ---- No cookie → 401 --------------------------------------------
    r = await client.get("/api/supervisor/sla-presets")
    assert r.status_code == 401, r.text
    r = await client.get("/api/supervisor/escalation-ladder")
    assert r.status_code == 401, r.text

    # ---- Wrong role: guest / servicer cookie → 403 ------------------
    g = await make_account("guest", f"wg-{uuid.uuid4().hex[:8]}", _PW)
    await login(g.username, _PW)
    assert (await client.get(
        "/api/supervisor/sla-presets")).status_code == 403
    sv = await make_account("servicer", f"ws-{uuid.uuid4().hex[:8]}", _PW)
    await login(sv.username, _PW)
    assert (await client.post(
        "/api/supervisor/escalation-ladder",
        json={"duty_manager_account_id": str(duty.id),
              "n_cycle_bound": 3})).status_code == 403

    await login(sup.username, _PW)

    # ===================================================================
    # SLA PRESETS
    # ===================================================================
    # ---- POST valid → 201 + ONE sla_preset_created event ------------
    rp = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert rp.status_code == 201, rp.text
    sla = rp.json()
    sla_id = sla["id"]
    assert sla["tier"] == "P1"
    assert sla["status"] == "active"
    await db.commit()
    n = (await db.execute(
        sa.select(sa.func.count()).select_from(EventSlaPresetCreated)
        .where(EventSlaPresetCreated.sla_preset_id == uuid.UUID(sla_id))
    )).scalar_one()
    assert n == 1

    # ---- GET → 200 lists -------------------------------------------
    lst = await client.get("/api/supervisor/sla-presets")
    assert lst.status_code == 200, lst.text
    assert sla_id in {row["id"] for row in lst.json()}

    # ---- duplicate ACTIVE (property,tier) → 409 (service guard) -----
    dup = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 60, "fulfilment_sla_seconds": 600,
        "supervisor_sla_seconds": 300})
    assert dup.status_code == 409, dup.text

    # A different tier on the same (server-resolved) property is fine.
    ok2 = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P2",
        "accept_window_seconds": 60, "fulfilment_sla_seconds": 600,
        "supervisor_sla_seconds": 300})
    assert ok2.status_code == 201, ok2.text

    # ---- incoherent durations (≤ 0) → 422 --------------------------
    # _validate_sla (422) runs BEFORE the duplicate-active check (409), so
    # an incoherent P1 still 422s even though P1 is active on the property.
    bad = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 0, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert bad.status_code == 422, bad.text
    bad2 = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": -1,
        "supervisor_sla_seconds": 900})
    assert bad2.status_code == 422, bad2.text
    # bad tier enum → 422
    badt = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P9",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900})
    assert badt.status_code == 422, badt.text
    # extra="forbid" → 422
    bade = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 120, "fulfilment_sla_seconds": 1800,
        "supervisor_sla_seconds": 900, "bogus": 1})
    assert bade.status_code == 422, bade.text

    # ---- PATCH durations → 200 + ONE sla_preset_updated event ------
    rpa = await client.patch(f"/api/supervisor/sla-presets/{sla_id}", json={
        "fulfilment_sla_seconds": 3600})
    assert rpa.status_code == 200, rpa.text
    assert rpa.json()["fulfilment_sla_seconds"] == 3600
    await db.commit()
    nu = (await db.execute(
        sa.select(sa.func.count()).select_from(EventSlaPresetUpdated)
        .where(EventSlaPresetUpdated.sla_preset_id == uuid.UUID(sla_id))
    )).scalar_one()
    assert nu == 1

    # ---- PATCH incoherent duration → 422 ---------------------------
    rpbad = await client.patch(f"/api/supervisor/sla-presets/{sla_id}", json={
        "supervisor_sla_seconds": 0})
    assert rpbad.status_code == 422, rpbad.text

    # ---- PATCH status=disabled disables (NO DELETE) ----------------
    rpd = await client.patch(f"/api/supervisor/sla-presets/{sla_id}", json={
        "status": "disabled"})
    assert rpd.status_code == 200, rpd.text
    assert rpd.json()["status"] == "disabled"
    await db.commit()
    # Now the P1 slot is free again → re-create succeeds (201).
    again = await client.post("/api/supervisor/sla-presets", json={
        "tier": "P1",
        "accept_window_seconds": 90, "fulfilment_sla_seconds": 900,
        "supervisor_sla_seconds": 450})
    assert again.status_code == 201, again.text

    # ---- unknown id PATCH → 404 ------------------------------------
    r404 = await client.patch(
        f"/api/supervisor/sla-presets/{uuid.uuid4()}",
        json={"fulfilment_sla_seconds": 10})
    assert r404.status_code == 404, r404.text

    # ---- DELETE any sla-presets route → 405 ------------------------
    assert (await client.delete(
        "/api/supervisor/sla-presets")).status_code == 405
    assert (await client.delete(
        f"/api/supervisor/sla-presets/{sla_id}")).status_code == 405

    # ===================================================================
    # ESCALATION LADDER
    # ===================================================================
    # ---- POST valid → 201 + ONE escalation_ladder_created event ----
    rl = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": 3})
    assert rl.status_code == 201, rl.text
    lad = rl.json()
    lad_id = lad["id"]
    assert lad["n_cycle_bound"] == 3
    assert lad["status"] == "active"
    await db.commit()
    nl = (await db.execute(
        sa.select(sa.func.count()).select_from(EventEscalationLadderCreated)
        .where(EventEscalationLadderCreated.escalation_ladder_id
               == uuid.UUID(lad_id))
    )).scalar_one()
    assert nl == 1

    # ---- GET → 200 lists -------------------------------------------
    llst = await client.get("/api/supervisor/escalation-ladder")
    assert llst.status_code == 200, llst.text
    assert lad_id in {row["id"] for row in llst.json()}

    # ---- duplicate ACTIVE ladder for property → 409 ----------------
    ldup = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": 5})
    assert ldup.status_code == 409, ldup.text
    # (Cross-property "different property is fine" is no longer reachable
    # via the API in single-property v1 — the property is server-resolved.
    # The per-property partial-unique index is asserted at the model level.)

    # ---- n_cycle_bound ≤ 0 → 422 -----------------------------------
    # _validate_ladder (422) runs BEFORE the duplicate-active check (409).
    lbad = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": 0})
    assert lbad.status_code == 422, lbad.text
    lbad2 = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": -3})
    assert lbad2.status_code == 422, lbad2.text
    # extra="forbid" → 422
    lbade = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": 3, "bogus": 1})
    assert lbade.status_code == 422, lbade.text

    # ---- PATCH n_cycle_bound → 200 + ONE escalation_ladder_updated -
    rlpa = await client.patch(
        f"/api/supervisor/escalation-ladder/{lad_id}",
        json={"n_cycle_bound": 7})
    assert rlpa.status_code == 200, rlpa.text
    assert rlpa.json()["n_cycle_bound"] == 7
    await db.commit()
    nlu = (await db.execute(
        sa.select(sa.func.count()).select_from(EventEscalationLadderUpdated)
        .where(EventEscalationLadderUpdated.escalation_ladder_id
               == uuid.UUID(lad_id))
    )).scalar_one()
    assert nlu == 1

    # ---- PATCH n_cycle_bound ≤ 0 → 422 -----------------------------
    rlbad = await client.patch(
        f"/api/supervisor/escalation-ladder/{lad_id}",
        json={"n_cycle_bound": 0})
    assert rlbad.status_code == 422, rlbad.text

    # ---- PATCH status=disabled disables (NO DELETE) ----------------
    rld = await client.patch(
        f"/api/supervisor/escalation-ladder/{lad_id}",
        json={"status": "disabled"})
    assert rld.status_code == 200, rld.text
    assert rld.json()["status"] == "disabled"
    await db.commit()
    # Slot freed → re-create succeeds.
    lagain = await client.post("/api/supervisor/escalation-ladder", json={
        "duty_manager_account_id": str(duty.id),
        "n_cycle_bound": 4})
    assert lagain.status_code == 201, lagain.text

    # ---- unknown id PATCH → 404 ------------------------------------
    rl404 = await client.patch(
        f"/api/supervisor/escalation-ladder/{uuid.uuid4()}",
        json={"n_cycle_bound": 9})
    assert rl404.status_code == 404, rl404.text

    # ---- DELETE any escalation-ladder route → 405 ------------------
    assert (await client.delete(
        "/api/supervisor/escalation-ladder")).status_code == 405
    assert (await client.delete(
        f"/api/supervisor/escalation-ladder/{lad_id}")).status_code == 405
