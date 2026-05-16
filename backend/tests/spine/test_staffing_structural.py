"""Staffing structural guards — the whole-classes-of-change net (spec §11).

These guards trip on regressions no one wrote a case for. They extend
"pass ⇒ no manual re-check" to whole CLASSES of drift (route/contract drift,
response-shape leak, role-gap, append-only violation, accidental hard-delete)
so a regression introduced by a LATER slice trips here without anyone adding
a test.

The six ADDED staffing-specific guards (spec §11 (1)-(6)):

  (1) route/contract snapshot   — ``test_route_contract_snapshot``
  (2) response parse-back       — ``test_staff_response_parse_back_no_internals``
  (3) role×endpoint matrix      — ``test_role_endpoint_matrix``
  (4) append-only guard         — ``test_append_only_one_event_one_detail``
  (5) no-DELETE → 405 sweep     — ``test_no_delete_sweep``
  (6) named-exception guard     — ``test_named_exception_single_dal_delete``

INHERITED (asserted/referenced here, NOT re-implemented):

  - the auth-coverage meta-test
    (``tests/api/test_security_guards.py::test_no_endpoint_is_unauthenticated_by_accident``)
    already auto-sweeps every new supervisor + servicer route — an ungated
    route fails there automatically. Guard (3) below adds the *exact*
    spec-§8 allow/deny matrix on top (not just "is it gated").
  - the merged event-writer append-only path guard
    (``tests/spine/test_structural_guards.py::test_no_event_update_or_delete_path``)
    asserts the ``shared/events`` writer source has no UPDATE/DELETE path.
    Guard (4) below adds the staffing-specific *behavioural* assertion
    (exactly one Event + one detail row per staffing mutation).
  - the leak sentinel (``test_structural_guards.py::test_leak_sentinel``)
    and the inherited route-only snapshot
    (``tests/api/test_security_guards.py::test_contract_snapshot_matches``)
    stay untouched; guard (1) here is a SEPARATE, staffing-scoped, RICHER
    snapshot (it additionally captures status code + response schema name)
    living under ``tests/spine/__snapshots__/route_contract.json``.

Reuses the merged ``tests/spine/conftest.py`` savepoint-rollback isolation
and the exact ``client`` / ``make_account`` / ``login`` fixtures Task 5/6/7
used in ``test_staffing_api.py`` — no fabricated auth harness.
"""
from __future__ import annotations

import json
import pathlib
import typing
import uuid

import sqlalchemy as sa
from fastapi.routing import APIRoute
from freezegun import freeze_time

from conduit.supervisor.schemas.staff import StaffOut

_PW = "pw-123456"

# Every route whose path starts with one of these is staffing surface.
_STAFFING_PREFIXES = (
    "/api/supervisor/staff",
    "/api/supervisor/rosters",
    "/api/servicer/",
)

_SNAP = (
    pathlib.Path(__file__).parent / "__snapshots__" / "route_contract.json"
)


# --------------------------------------------------------------------------
# App introspection helpers (no fabricated harness; pure FastAPI metadata).
# --------------------------------------------------------------------------
def _schema_name(response_model: object) -> str | None:
    """Stable, human-meaningful name for a route's ``response_model``.

    ``list[StaffOut]`` → ``"list[StaffOut]"``; a bare model → its
    ``__name__``; ``None`` → ``None``. Deterministic so the snapshot is
    stable across runs."""
    if response_model is None:
        return None
    origin = typing.get_origin(response_model)
    if origin in (list,):
        (arg,) = typing.get_args(response_model)
        return f"list[{getattr(arg, '__name__', repr(arg))}]"
    return getattr(response_model, "__name__", repr(response_model))


def _is_staffing(path: str) -> bool:
    return any(path.startswith(p) for p in _STAFFING_PREFIXES)


def _route_contract() -> list[list]:
    """Sorted ``[method, path, sorted(status codes), schema name]`` for every
    staffing route. The status-code set is the route's declared success code
    (``status_code`` or the 200 default) unioned with any explicitly declared
    ``responses`` keys — captured sorted so an added/changed status trips."""
    from conduit.main import app

    rows: list[list] = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if not _is_staffing(r.path):
            continue
        codes = {int(c) for c in (r.responses or {})}
        codes.add(int(r.status_code or 200))
        schema = _schema_name(r.response_model)
        for m in sorted(r.methods):
            if m in ("HEAD", "OPTIONS"):
                continue
            rows.append([m, r.path, sorted(codes), schema])
    rows.sort(key=lambda x: (x[1], x[0]))
    return rows


# --------------------------------------------------------------------------
# Shared per-role login helpers (reuse the merged fixtures only).
# --------------------------------------------------------------------------
async def _seed_property_section(db):
    from conduit.shared.models import Property, Section

    p = Property(name=f"P-{uuid.uuid4().hex[:8]}")
    db.add(p)
    await db.flush()
    sec = Section(property_id=p.id, label=f"S-{uuid.uuid4().hex[:6]}")
    db.add(sec)
    await db.flush()
    return p, sec


# ==========================================================================
# Guard (1) — route/contract snapshot (spec §11(1), §4 friction).
# First run writes the file IF ABSENT, then skips; every subsequent run
# ENFORCES against the committed snapshot. A real drift FAILS — it never
# silently overwrites a committed snapshot (the write-if-absent path is the
# only writer, guarded by ``not _SNAP.exists()``).
# ==========================================================================
def test_route_contract_snapshot():
    current = _route_contract()
    if not _SNAP.exists():
        _SNAP.parent.mkdir(parents=True, exist_ok=True)
        _SNAP.write_text(json.dumps(current, indent=2) + "\n")
        import pytest

        pytest.skip("staffing route-contract snapshot created; "
                    "commit it and re-run to enforce")
    saved = json.loads(_SNAP.read_text())
    # Normalise both sides to JSON-roundtripped lists for an exact compare.
    saved_norm = json.loads(json.dumps(saved))
    current_norm = json.loads(json.dumps(current))
    if saved_norm != current_norm:
        # Build a readable diff of the changed contract rows.
        saved_set = {tuple(r[:2]) for r in saved_norm}
        cur_set = {tuple(r[:2]) for r in current_norm}
        added = sorted(cur_set - saved_set)
        removed = sorted(saved_set - cur_set)
        changed = []
        saved_map = {tuple(r[:2]): r for r in saved_norm}
        cur_map = {tuple(r[:2]): r for r in current_norm}
        for key in sorted(saved_set & cur_set):
            if saved_map[key] != cur_map[key]:
                changed.append((key, saved_map[key], cur_map[key]))
        raise AssertionError(
            "staffing route/contract drift detected.\n"
            f"  added routes:   {added}\n"
            f"  removed routes: {removed}\n"
            f"  changed rows:   {changed}\n"
            "regenerate the snapshot if this change was intentional "
            "(spec §4): delete "
            f"{_SNAP} and re-run."
        )


# ==========================================================================
# Guard (2) — response parse-back / no account-internals leak (spec §11(2),
# §8). The StaffOut join must never serialize account internals; the
# ``extra="forbid"`` schema must parse the live payload back unchanged.
# ==========================================================================
async def test_staff_response_parse_back_no_internals(
    client, make_account, login
):
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    await login(sup.username, _PW)
    await client.post(
        f"/api/supervisor/staff/{srv.id}/profile",
        json={"staff_class": "engineering"},
    )
    await client.put(
        f"/api/supervisor/staff/{srv.id}/skills",
        json={"skills": ["hvac", "electrical"]},
    )
    r = await client.get("/api/supervisor/staff")
    assert r.status_code == 200, r.text
    body = r.json()
    # Parse-back through the extra="forbid" schema — red on any shape drift
    # (renamed/added field, internal field surfacing through the join).
    for row in body:
        StaffOut(**row)
    # Account internals never leak through the join — raw text + per-row.
    assert "secret_hash" not in r.text
    for row in body:
        for forbidden in ("secret_hash", "username", "password"):
            assert forbidden not in row, (
                f"account internal {forbidden!r} leaked through StaffOut"
            )


# ==========================================================================
# Guard (3) — role×endpoint matrix (spec §11(3), §8). Every staffing
# endpoint as guest / servicer / supervisor / duty_manager / unauth; assert
# the EXACT spec-§8 allow/deny matrix. Inherited free is only "is it gated";
# this asserts the precise allow set + deny code (403 wrong-role, 401
# unauth). A non-target status (e.g. 200 where 403 is required) trips.
# ==========================================================================
async def test_role_endpoint_matrix(client, make_account, login, db):
    # Representative concrete request per endpoint class. Auth/role is
    # decided BEFORE body validation, so a minimal body is fine: we
    # assert the request is ALLOWED (not 401/403) or DENIED (401/403),
    # never the downstream 2xx/4xx business code.
    await _seed_property_section(db)
    rid = uuid.uuid4()
    aid = uuid.uuid4()
    acc = uuid.uuid4()

    # (method, path, json) for the supervisor staff+rosters surface.
    sup_calls = [
        ("GET", "/api/supervisor/staff", None),
        ("GET", f"/api/supervisor/staff/{acc}", None),
        ("POST", f"/api/supervisor/staff/{acc}/profile",
         {"staff_class": "housekeeping"}),
        ("PATCH", f"/api/supervisor/staff/{acc}/profile",
         {"status": "disabled"}),
        ("PUT", f"/api/supervisor/staff/{acc}/skills", {"skills": []}),
        ("GET", "/api/supervisor/rosters", None),
        ("POST", "/api/supervisor/rosters",
         {"shift_start": "2026-05-16T08:00:00+00:00",
          "shift_end": "2026-05-16T16:00:00+00:00"}),
        ("PATCH", f"/api/supervisor/rosters/{rid}", {"status": "disabled"}),
        ("GET", f"/api/supervisor/rosters/{rid}/assignments", None),
        ("POST", f"/api/supervisor/rosters/{rid}/assignments",
         {"account_id": str(acc), "assignment": "member"}),
        ("PATCH", f"/api/supervisor/rosters/{rid}/assignments/{aid}",
         {"status": "disabled"}),
    ]
    # The servicer self surface (spec §8 "Servicer — self").
    svc_calls = [
        ("GET", "/api/servicer/home", None),
        ("PUT", "/api/servicer/presence", {"presence": "working"}),
    ]

    async def _do(method, path, body):
        return await client.request(method, path, json=body)

    # --- unauthenticated: everything 401 (no cookie). ---------------------
    client.cookies.clear()
    for method, path, body in sup_calls + svc_calls:
        r = await _do(method, path, body)
        assert r.status_code == 401, (
            f"unauth {method} {path} -> {r.status_code} (want 401)"
        )

    # --- guest: denied everywhere (wrong role → 403). ---------------------
    guest = await make_account("guest", f"g-{uuid.uuid4().hex[:8]}", _PW)
    await login(guest.username, _PW)
    for method, path, body in sup_calls + svc_calls:
        r = await _do(method, path, body)
        assert r.status_code == 403, (
            f"guest {method} {path} -> {r.status_code} (want 403)"
        )

    # --- servicer: DENIED on supervisor surface, ALLOWED on self. --------
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)
    await login(srv.username, _PW)
    for method, path, body in sup_calls:
        r = await _do(method, path, body)
        assert r.status_code == 403, (
            f"servicer {method} {path} -> {r.status_code} (want 403)"
        )
    for method, path, body in svc_calls:
        r = await _do(method, path, body)
        assert r.status_code not in (401, 403, 500), (
            f"servicer {method} {path} -> {r.status_code} "
            "(must be allowed past the role gate; 500 = regression)"
        )

    # --- supervisor & duty_manager: ALLOWED on supervisor surface,
    #     DENIED on the servicer self surface. -----------------------------
    for role in ("supervisor", "duty_manager"):
        actor = await make_account(
            role, f"{role}-{uuid.uuid4().hex[:8]}", _PW
        )
        await login(actor.username, _PW)
        for method, path, body in sup_calls:
            r = await _do(method, path, body)
            assert r.status_code not in (401, 403, 500), (
                f"{role} {method} {path} -> {r.status_code} "
                "(must be allowed past the role gate; 500 = regression)"
            )
        for method, path, body in svc_calls:
            r = await _do(method, path, body)
            assert r.status_code == 403, (
                f"{role} {method} {path} -> {r.status_code} (want 403)"
            )


# ==========================================================================
# Guard (4) — append-only guard (spec §11(4)). After a create_profile call
# through the real service, EXACTLY one Event row and EXACTLY one matching
# detail row exist for it (within the test transaction). Complements the
# inherited writer-source guard (no UPDATE/DELETE path) with the staffing
# behavioural assertion (one event + one detail per mutation).
# ==========================================================================
async def test_append_only_one_event_one_detail(make_account, db):
    from conduit.shared.models import Event, EventStaffProfileCreated
    from conduit.supervisor.services import staff as staff_svc

    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)

    await staff_svc.create_profile(
        db,
        uuid.UUID(str(sup.id)),
        uuid.UUID(str(srv.id)),
        staff_class="housekeeping",
    )
    await db.flush()

    details = (
        await db.execute(
            sa.select(EventStaffProfileCreated).where(
                EventStaffProfileCreated.account_id == srv.id
            )
        )
    ).scalars().all()
    assert len(details) == 1, (
        f"expected exactly 1 staff_profile_created detail, got {len(details)}"
    )
    events = (
        await db.execute(
            sa.select(Event).where(
                Event.id == details[0].event_id,
                Event.type == "staff_profile_created",
            )
        )
    ).scalars().all()
    assert len(events) == 1, (
        f"expected exactly 1 matching event row, got {len(events)}"
    )
    assert str(events[0].actor_account_id) == str(sup.id)


# ==========================================================================
# Guard (5) — no-DELETE → 405 sweep (spec §11(5), §4 "Deletes"). For EVERY
# staffing path, an authenticated DELETE returns 405 (FastAPI: no DELETE
# handler registered). disable-not-delete is the only "remove".
# ==========================================================================
async def test_no_delete_sweep(client, make_account, login, db):
    await _seed_property_section(db)
    sup = await make_account("supervisor", f"s-{uuid.uuid4().hex[:8]}", _PW)
    srv = await make_account("servicer", f"srv-{uuid.uuid4().hex[:8]}", _PW)

    # Distinct concrete paths for every staffing route template.
    rid = uuid.uuid4()
    aid = uuid.uuid4()
    paths = [
        "/api/supervisor/staff",
        f"/api/supervisor/staff/{srv.id}",
        f"/api/supervisor/staff/{srv.id}/profile",
        f"/api/supervisor/staff/{srv.id}/skills",
        "/api/supervisor/rosters",
        f"/api/supervisor/rosters/{rid}",
        f"/api/supervisor/rosters/{rid}/assignments",
        f"/api/supervisor/rosters/{rid}/assignments/{aid}",
        "/api/servicer/home",
        "/api/servicer/presence",
    ]

    # As supervisor (authenticated) — DELETE must be 405 on the supervisor
    # surface; the servicer paths are 405 (route exists, no DELETE) before
    # any role check matters because method routing precedes the gate.
    await login(sup.username, _PW)
    for p in paths:
        r = await client.delete(p)
        assert r.status_code == 405, (
            f"DELETE {p} -> {r.status_code} (want 405; no hard-delete)"
        )

    # And as servicer for the servicer self surface (its own role).
    # DELETE→405 is method routing, which precedes auth/time, so a single
    # login is sufficient (no duplicate login; freeze_time kept minimal as
    # it does not affect this method-routing assertion).
    with freeze_time("2026-05-16T10:00:00+00:00"):
        await login(srv.username, _PW)
        for p in ("/api/servicer/home", "/api/servicer/presence"):
            r = await client.delete(p)
            assert r.status_code == 405, (
                f"DELETE {p} (servicer) -> {r.status_code} (want 405)"
            )


# ==========================================================================
# Guard (6) — named-exception guard (spec §11(6), §4 "Skills named
# exception" / "Deletes"). The SQLAlchemy ``delete`` construct may be
# called in EXACTLY ONE place across every ``conduit/**/dal/*.py`` —
# ``supervisor/dal/staff.py`` inside ``replace_skills``. Anything else
# hard-deleting trips this.
#
# This is a full alias-resolving AST scan over EVERY DAL module — there is
# NO substring pre-filter that could short-circuit a pass. A regression
# such as ``from sqlalchemy import delete as _del`` + ``_del(Roster)`` in
# another DAL module (which produces neither ``"delete("`` nor
# ``".delete()"``) is still caught because we resolve the name bound to
# SQLAlchemy's ``delete`` per-module, not by source text.
# ==========================================================================
def test_named_exception_single_dal_delete():
    import ast

    import conduit

    dal_root = pathlib.Path(conduit.__file__).parent
    # The single sanctioned (path-tail, function) hard-delete site.
    _SANCTIONED = ("supervisor/dal/staff.py", "replace_skills")

    def _tail(path: pathlib.Path) -> str:
        # Robust normalised path tail: ``<area>/dal/<module>.py``.
        return "/".join(path.parts[-3:])

    def _resolve_delete_call(
        node: ast.Call,
        bare_names: set[str],
        module_aliases: set[str],
    ) -> bool:
        """True iff this Call node invokes SQLAlchemy ``delete``.

        Handles three forms:
          - ``delete(...)`` / ``<asname>(...)`` where the name is bound via
            ``from sqlalchemy import delete [as X]``.
          - ``<sa>.delete(...)`` where ``<sa>`` is an ``import sqlalchemy``
            (optionally ``as sa``) module alias.
          - a direct ``.delete()`` method call on a query/session object
            (preserve the original guard's secondary intent).
        """
        fn = node.func
        if isinstance(fn, ast.Name):
            return fn.id in bare_names
        if isinstance(fn, ast.Attribute):
            # ``sqlalchemy.delete(...)`` / ``sa.delete(...)``.
            if (
                fn.attr == "delete"
                and isinstance(fn.value, ast.Name)
                and fn.value.id in module_aliases
            ):
                return True
            # Bare ``.delete()`` method call (e.g. ``q.delete()``) — the
            # original guard's secondary concern; kept so a method-style
            # hard-delete in another DAL still trips.
            if fn.attr == "delete":
                return True
        return False

    sites: set[tuple[str, str]] = set()
    for path in sorted(dal_root.glob("**/dal/*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))

        # --- Per-module alias resolution. --------------------------------
        bare_names: set[str] = set()      # names bound to sqlalchemy.delete
        module_aliases: set[str] = set()  # aliases for the sqlalchemy module
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "sqlalchemy":
                    for alias in node.names:
                        if alias.name == "delete":
                            bare_names.add(alias.asname or "delete")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "sqlalchemy":
                        module_aliases.add(alias.asname or "sqlalchemy")

        # --- Map every Call node to its nearest enclosing function. ------
        func_of_call: dict[int, str] = {}
        for fdef in ast.walk(tree):
            if isinstance(fdef, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(fdef):
                    if isinstance(child, ast.Call):
                        # Innermost wins: an inner def re-binds later.
                        func_of_call[id(child)] = fdef.name

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _resolve_delete_call(node, bare_names, module_aliases):
                continue
            sites.add((_tail(path), func_of_call.get(id(node), "<module>")))

    expected = {_SANCTIONED}
    assert sites == expected, (
        "SQLAlchemy delete() may be called in EXACTLY ONE DAL site "
        "(spec §4 'Skills named exception' / 'Deletes'): "
        f"{_SANCTIONED[0]}::{_SANCTIONED[1]}. "
        f"offending/missing site set: found={sorted(sites)} "
        f"expected={sorted(expected)}"
    )
