# Conversation Context + Answer↔Action Seam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **SUBAGENT POLICY (mandatory):** Every dispatched subagent MUST be an **Opus** subagent (`model: opus`) — never sonnet or haiku. Every dispatch MUST paste that task's exact **Files** list into the subagent prompt and instruct it to touch only those files. This slice has a large, spine-coupled surface; an under-powered or unscoped agent will break the in-flight spine.

**Goal:** Give the guest a real multi-turn conversation (a sliding 50-message context window fed to the LLM, extraction-only) and complete the answer↔action seam so a reservation follow-up ("late checkout till 2pm?") flows through the escalation spine and mutates `stay.check_out` on supervisor approval or silent auto-proceed.

**Architecture:** Stacks **on top of the in-flight dispatch-spine branch** (not `main`). The context window is a pure `shared/domain` function consumed by the intake service; the mutation is a new typed recommendation action threaded additively through the spine's existing single executor (`apply_recommendation`). Extraction-only: the deterministic risk rulebook is unchanged. Zero new API endpoints. Closure reuses the merged closure-lite path (no new child states).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Postgres, pytest/pytest-asyncio, savepoint-rollback test isolation, OpenAI Responses API (bulkheaded), React/TS/Vite (one field variant only).

**Source of truth:** the design spec at `docs/superpowers/specs/2026-05-16-conversation-context-answer-action-design.md` (read it before starting). Product decisions are cited by their D-series IDs as they appear in the existing Conduit code comments; do not look outside this repository for them.

**Base branch:** `feat/dispatch-spine`. **New branch:** `feat/conversation-answer-action`. **Worktree:** `/workspace/Conduit-conversation-answer-action`. The PR targets `feat/dispatch-spine` (this slice stacks on the spine; it cannot target `main` until the spine merges).

---

## Pre-flight: exact facts verified against the spine worktree (do not re-derive)

- Migration `0005`'s **revision id is `"0005_dispatch"`** (the *filename* is `0005_dispatch_spine.py`). The new migration's `down_revision` MUST be `"0005_dispatch"`.
- `guest/dal/children.insert_child(s, **f)` is a generic `ChildSubRequest(**f)` passthrough — adding the model column needs **no DAL change**.
- `NoDispatchResolution.ck_ndr_mode` is `('grounded_answer','human_deferral')` — closure-lite reuse needs it widened to add `'reservation_mutation'` (additive).
- The spine intake `flag` branch currently parks the child (`emit_child "child_parked"` → `{"terminal":"logged"}`); it does **not** open an escalation. This slice wires the **reservation-mutation case only** to `spine.open_escalation` (non-mutation flags keep byte-identical park behaviour — back-compat, minimal blast radius).
- `shared/engine/spine.py` already imports `Request`, `Stay`, `sa`, `writer`, `lifecycle`; add `NoDispatchResolution`, `RecApplyReservationMutation` to its model import.
- Tests live in `backend/tests/spine/`; `conftest.py` provides the `fake_llm` fixture (`state["classify"]`/`state["ground"]` async callables) and unconditional savepoint rollback. Use them.
- `recommendation.build` is called positionally as `build(trigger=..., child=..., context=...)`; `child` may be a dict in pure tests. Context for `triage_flag` is assembled by `spine._assemble_context`.

---

### Task 0: Worktree, environment, and .env setup

**Files:**
- Create: worktree at `/workspace/Conduit-conversation-answer-action` (branch `feat/conversation-answer-action` off `feat/dispatch-spine`)
- Copy: `/workspace/Conduit/backend/.venv` → worktree; `/workspace/Conduit/backend/.env`, `/workspace/Conduit/frontend/.env` → worktree

- [ ] **Step 1: Create the worktree off the spine branch**

```bash
cd /workspace/Conduit
git fetch --all
git worktree add -b feat/conversation-answer-action \
  /workspace/Conduit-conversation-answer-action feat/dispatch-spine
cd /workspace/Conduit-conversation-answer-action
git rev-parse --abbrev-ref HEAD   # expect: feat/conversation-answer-action
git log --oneline -1              # expect: the spine HEAD commit (515b07b ...)
```

- [ ] **Step 2: Seed the venv from the source venv and repoint editable installs**

```bash
cp -r /workspace/Conduit/backend/.venv \
  /workspace/Conduit-conversation-answer-action/backend/.venv
cd /workspace/Conduit-conversation-answer-action/backend
# Repoint the editable install (.pth/egg-link) at the new worktree path:
.venv/bin/pip install -e ".[dev]" --no-deps
.venv/bin/python -c "import conduit, pathlib; print(pathlib.Path(conduit.__file__).resolve())"
# expect a path under /workspace/Conduit-conversation-answer-action/backend/
```

Expected: the printed path is inside the new worktree (not the source repo). If it points at the source, run `.venv/bin/pip install -e ".[dev]"` (without `--no-deps`) and re-check.

- [ ] **Step 3: Copy the env files**

```bash
cp /workspace/Conduit/backend/.env \
  /workspace/Conduit-conversation-answer-action/backend/.env
cp /workspace/Conduit/frontend/.env \
  /workspace/Conduit-conversation-answer-action/frontend/.env
ls -l /workspace/Conduit-conversation-answer-action/backend/.env \
      /workspace/Conduit-conversation-answer-action/frontend/.env
```

- [ ] **Step 4: Baseline — the inherited suite is green before any change**

```bash
cd /workspace/Conduit-conversation-answer-action/backend
.venv/bin/pytest -q
```

Expected: PASS (the spine bench is green). If red here, STOP — the base branch is broken; do not build on it. Record the failure and surface it.

> **All subsequent tasks run inside `/workspace/Conduit-conversation-answer-action/backend` unless a path says `frontend/`. All `pytest`/`alembic`/`git` commands use `.venv/bin/...`.**

---

### Task 1: Settings constant `conversation_window`

**Files:**
- Modify: `backend/conduit/core/config.py` (the `Settings` class)
- Test: `backend/tests/spine/test_conversation_window.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_conversation_window.py
from conduit.core.config import get_settings


def test_conversation_window_default_is_50():
    assert get_settings().conversation_window == 50
```

- [ ] **Step 2: Run it, verify it fails**

Run: `.venv/bin/pytest tests/spine/test_conversation_window.py -q`
Expected: FAIL (`AttributeError: ... 'conversation_window'`).

- [ ] **Step 3: Add the field**

In `backend/conduit/core/config.py`, in `class Settings`, directly after the `engine_poll_seconds: int = 10` line, add:

```python
    # Sliding conversation context window — number of most-recent transcript
    # messages (guest + system, either direction) fed to the LLM as
    # extraction-only prompt context. Not supervisor CONFIG (YAGNI).
    conversation_window: int = 50
```

- [ ] **Step 4: Run it, verify it passes**

Run: `.venv/bin/pytest tests/spine/test_conversation_window.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/core/config.py backend/tests/spine/test_conversation_window.py
git commit -m "feat(config): conversation_window setting (default 50)"
```

---

### Task 2: Pure conversation-window assembly module

**Files:**
- Create: `backend/conduit/shared/domain/conversation.py`
- Test: `backend/tests/spine/test_conversation_domain.py`

The module is **pure** (no DB/session/clock — the `grounding.py` contract). Input: already-fetched, time-ordered transcript turns. Output: a bounded last-N string, oldest dropped past N, role-labelled.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/spine/test_conversation_domain.py
from conduit.shared.domain.conversation import Turn, window


def test_empty_yields_empty_string():
    assert window([], limit=50) == ""


def test_orders_and_labels_roles():
    turns = [Turn(role="guest", text="what time is checkout?"),
             Turn(role="system", text="11am")]
    assert window(turns, limit=50) == "guest: what time is checkout?\nsystem: 11am"


def test_sliding_keeps_only_last_n_oldest_dropped():
    turns = [Turn(role="guest", text=f"m{i}") for i in range(60)]
    out = window(turns, limit=50)
    lines = out.split("\n")
    assert len(lines) == 50
    assert lines[0] == "guest: m10"      # oldest 10 dropped
    assert lines[-1] == "guest: m59"


def test_pure_no_io():
    # Constructed from plain values; importing/calling touches no DB/session.
    import inspect
    import conduit.shared.domain.conversation as m
    src = inspect.getsource(m)
    assert "AsyncSession" not in src and "select(" not in src
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_conversation_domain.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the pure module**

```python
# backend/conduit/shared/domain/conversation.py
"""Conversation window — pure cross-portal domain (Spec §7.1).

Extraction-only (D5/D30): the bounded last-N transcript is prompt context
for the LLM's extraction; it never feeds the deterministic risk rulebook.
PURE: no DB, no session, no clock — the caller does the time-ordered read
(``rdal``/``cdal``/``resdal``) and hands rows in. Mirrors grounding.py:
"the DB read belongs to the caller, never here".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    role: str          # "guest" | "system"
    text: str


def window(turns: list[Turn], *, limit: int) -> str:
    """The last ``limit`` turns, chronological, role-labelled, oldest
    dropped past the bound. ``turns`` MUST already be time-ordered ascending
    by the caller."""
    kept = turns[-limit:] if limit and len(turns) > limit else list(turns)
    return "\n".join(f"{t.role}: {t.text}" for t in kept)
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_conversation_domain.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/conversation.py backend/tests/spine/test_conversation_domain.py
git commit -m "feat(domain): pure conversation.window (extraction-only, no DB)"
```

---

### Task 3: Model — `RecApplyReservationMutation` detail + widen `ck_rec_action`

**Files:**
- Modify: `backend/conduit/shared/models/recommendation.py`
- Modify: `backend/conduit/shared/models/__init__.py`
- Test: `backend/tests/spine/test_reservation_mutation_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_reservation_mutation_models.py
from conduit.shared import models as m


def test_rec_apply_reservation_mutation_exported_and_shaped():
    cls = m.RecApplyReservationMutation
    cols = cls.__table__.columns
    assert cls.__tablename__ == "rec_apply_reservation_mutation"
    assert "recommendation_escalation_id" in cols
    assert "field" in cols and "requested_value" in cols


def test_ck_rec_action_widened():
    rec = m.Recommendation
    ck = next(c for c in rec.__table__.constraints
              if getattr(c, "name", "") == "ck_rec_action")
    assert "apply_reservation_mutation" in str(ck.sqltext)
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: FAIL (`AttributeError: RecApplyReservationMutation`).

- [ ] **Step 3: Extend the recommendation model**

In `backend/conduit/shared/models/recommendation.py`:

(a) widen the `ck_rec_action` CheckConstraint string to include `apply_reservation_mutation`:

```python
        CheckConstraint(
            "action in ('reassign','broadcast','relocate',"
            "'extend_sla','approve','deny','apply_reservation_mutation')",
            name="ck_rec_action",
        ),
```

(b) append a new detail class after `RecBroadcast` (uses the existing `_RecDetail` base; add `CheckConstraint`, `DateTime` are already imported — `DateTime` is imported, `CheckConstraint` is imported):

```python
class RecApplyReservationMutation(_RecDetail):
    __tablename__ = "rec_apply_reservation_mutation"
    __table_args__ = (
        CheckConstraint("field = 'check_out'",
                        name="ck_rec_apply_mutation_field"),
    )
    field: Mapped[str] = mapped_column(String, nullable=False)
    requested_value: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
```

Add the imports this needs at the top of the file if absent: `import datetime as dt` (check the file — it currently imports `Integer, String`; add `import datetime as dt` near the other stdlib imports).

- [ ] **Step 4: Register in the models package**

In `backend/conduit/shared/models/__init__.py`: add `RecApplyReservationMutation` to the `from conduit.shared.models.recommendation import (...)` block (right after `RecBroadcast,`) and add `"RecApplyReservationMutation"` to `__all__` immediately after `"RecBroadcast"` in the `"RecApprove", "RecDeny", "RecBroadcast",` line.

- [ ] **Step 5: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/models/recommendation.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_reservation_mutation_models.py
git commit -m "feat(model): RecApplyReservationMutation detail + widen ck_rec_action (additive)"
```

---

### Task 4: Model — `EventReservationMutated` detail + widen `ck_event_type`

**Files:**
- Modify: `backend/conduit/shared/models/event.py`
- Modify: `backend/conduit/shared/models/__init__.py`
- Test: `backend/tests/spine/test_reservation_mutation_models.py` (extend)

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/spine/test_reservation_mutation_models.py`:

```python
def test_event_reservation_mutated_shaped():
    cls = m.EventReservationMutated
    cols = cls.__table__.columns
    assert cls.__tablename__ == "event_reservation_mutated"
    for c in ("event_id", "stay_id", "field", "old_value", "new_value"):
        assert c in cols


def test_ck_event_type_widened():
    ev = m.Event
    ck = next(c for c in ev.__table__.constraints
              if getattr(c, "name", "") == "ck_event_type")
    assert "reservation_mutated" in str(ck.sqltext)
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: FAIL (`AttributeError: EventReservationMutated`).

- [ ] **Step 3: Extend the event model**

In `backend/conduit/shared/models/event.py`:

(a) widen the `ck_event_type` CheckConstraint: in the long `type in (...)` string, append `,'reservation_mutated'` immediately before the closing `)` (i.e. after `'escalation_ladder_updated'`).

(b) append a new detail class at the end of the file (the file already imports `CheckConstraint, DateTime, String`):

```python
class EventReservationMutated(Base):
    __tablename__ = "event_reservation_mutated"
    __table_args__ = (
        CheckConstraint("field = 'check_out'",
                        name="ck_event_resv_mut_field"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    new_value: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Register in the models package**

In `backend/conduit/shared/models/__init__.py`: add `EventReservationMutated` to the `from conduit.shared.models.event import (...)` block (after `EventEscalationLadderUpdated,`) and add `"EventReservationMutated"` to `__all__` directly after `"EventEscalationLadderUpdated",`.

- [ ] **Step 5: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/models/event.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_reservation_mutation_models.py
git commit -m "feat(model): EventReservationMutated detail + widen ck_event_type (additive)"
```

---

### Task 5: Model — widen `ck_ndr_mode` + add `child_sub_request.requested_checkout`

**Files:**
- Modify: `backend/conduit/shared/models/no_dispatch_resolution.py`
- Modify: `backend/conduit/shared/models/child_sub_request.py`
- Test: `backend/tests/spine/test_reservation_mutation_models.py` (extend)

`requested_checkout` is the durable home of the LLM-extracted target so the **pure builder and the auto-proceed executor never call the LLM** (D5/D30 auto-proceed-safety). `ck_ndr_mode` is widened so closure-lite can be reused for the mutation outcome with zero new endpoints/states.

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/spine/test_reservation_mutation_models.py`:

```python
def test_child_has_requested_checkout_nullable():
    col = m.ChildSubRequest.__table__.columns["requested_checkout"]
    assert col.nullable is True


def test_ndr_mode_widened():
    ck = next(c for c in m.NoDispatchResolution.__table__.constraints
              if getattr(c, "name", "") == "ck_ndr_mode")
    assert "reservation_mutation" in str(ck.sqltext)
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: FAIL (`KeyError: 'requested_checkout'`).

- [ ] **Step 3: Add the column**

In `backend/conduit/shared/models/child_sub_request.py`, after the `predecessor_child_id` mapped_column block and before `created_at`, add:

```python
    requested_checkout: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
```

(`dt`, `DateTime` are already imported in that file.)

- [ ] **Step 4: Widen the resolution mode CHECK**

In `backend/conduit/shared/models/no_dispatch_resolution.py`, change the `ck_ndr_mode` constraint to:

```python
        CheckConstraint(
            "mode in ('grounded_answer','human_deferral',"
            "'reservation_mutation')", name="ck_ndr_mode"),
```

- [ ] **Step 5: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_reservation_mutation_models.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/models/child_sub_request.py backend/conduit/shared/models/no_dispatch_resolution.py backend/tests/spine/test_reservation_mutation_models.py
git commit -m "feat(model): child.requested_checkout + widen ck_ndr_mode (additive)"
```

---

### Task 6: Migration `0006`

**Files:**
- Create: `backend/migrations/versions/0006_conversation_answer_action.py`
- Test: `backend/tests/spine/test_migration_0006.py`

Mirror the hand-audited drop+recreate-CHECK idiom of `0005_dispatch_spine.py` (autogenerate cannot detect CHECK-text changes). `down_revision = "0005_dispatch"`.

- [ ] **Step 1: Write the failing migration test**

```python
# backend/tests/spine/test_migration_0006.py
import subprocess


def _alembic(*args):
    return subprocess.run(["/workspace/Conduit-conversation-answer-action/"
                           "backend/.venv/bin/alembic", *args],
                          cwd="/workspace/Conduit-conversation-answer-action/"
                          "backend", capture_output=True, text=True)


def test_revision_chain():
    from migrations.versions import (  # noqa
        __dict__ as _)  # ensure package import works
    import importlib
    mod = importlib.import_module(
        "migrations.versions.0006_conversation_answer_action".replace(
            "0006_conversation_answer_action",
            "0006_conversation_answer_action"))
    assert mod.down_revision == "0005_dispatch"
    assert mod.revision == "0006_conv_aa"


def test_upgrade_downgrade_roundtrips():
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _alembic("downgrade", "0005_dispatch")
    assert down.returncode == 0, down.stderr
    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, up2.stderr
```

> If the dynamic import line is awkward in your environment, replace `test_revision_chain` with reading the file text and asserting it contains `down_revision: str | None = "0005_dispatch"` and `revision: str = "0006_conv_aa"`.

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_migration_0006.py -q`
Expected: FAIL (migration module missing).

- [ ] **Step 3: Write the migration**

```python
# backend/migrations/versions/0006_conversation_answer_action.py
"""0006 conversation context + answer<->action seam

Revision ID: 0006_conv_aa
Revises: 0005_dispatch
Create Date: 2026-05-16

Additive on the spine: 2 detail tables (rec_apply_reservation_mutation,
event_reservation_mutated), 1 nullable child column (requested_checkout),
and 3 drop+recreate CHECK widenings (ck_rec_action, ck_event_type,
ck_ndr_mode) — autogenerate cannot detect CHECK-text changes, mirroring the
0003/0004/0005 hand-written idiom. No data migration; existing rows survive.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_conv_aa"
down_revision: str | None = "0005_dispatch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "child_sub_request",
        sa.Column("requested_checkout", sa.DateTime(timezone=True),
                  nullable=True))

    op.create_table(
        "rec_apply_reservation_mutation",
        sa.Column("recommendation_escalation_id", sa.Uuid(),
                  sa.ForeignKey("recommendation.escalation_id"),
                  primary_key=True),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("requested_value", sa.DateTime(timezone=True),
                  nullable=False),
        sa.CheckConstraint("field = 'check_out'",
                           name="ck_rec_apply_mutation_field"))

    op.create_table(
        "event_reservation_mutated",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"),
                  primary_key=True),
        sa.Column("stay_id", sa.Uuid(), sa.ForeignKey("stay.id"),
                  nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("old_value", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_value", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("field = 'check_out'",
                           name="ck_event_resv_mut_field"))

    # --- drop + recreate the 3 widened CHECKs (text change undetectable) ---
    op.drop_constraint("ck_rec_action", "recommendation", type_="check")
    op.create_check_constraint(
        "ck_rec_action", "recommendation",
        "action in ('reassign','broadcast','relocate','extend_sla',"
        "'approve','deny','apply_reservation_mutation')")

    op.drop_constraint("ck_ndr_mode", "no_dispatch_resolution",
                       type_="check")
    op.create_check_constraint(
        "ck_ndr_mode", "no_dispatch_resolution",
        "mode in ('grounded_answer','human_deferral','reservation_mutation')")

    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "event",
        "type in ('stay_created','stay_ended','guest_relocated',"
        "'request_created','child_triaged','child_answered',"
        "'child_deferred','child_parked','child_closed','child_reopened',"
        "'staff_profile_created','staff_profile_updated',"
        "'staff_skills_set','roster_created','roster_updated',"
        "'assignment_created','assignment_updated','presence_changed',"
        "'work_order_created','work_order_pushed','work_order_broadcast',"
        "'work_order_accepted','work_order_in_progress',"
        "'work_order_completed','work_order_cancelled','child_routed',"
        "'child_done_pending_confirm','child_closed_confirmed',"
        "'child_reopened_by_guest','child_cancelled','escalation_opened',"
        "'escalation_resolved','recommendation_created','glitch_opened',"
        "'glitch_closed','cross_dept_notified','timer_fired',"
        "'sla_preset_created','sla_preset_updated',"
        "'escalation_ladder_created','escalation_ladder_updated',"
        "'reservation_mutated')")


def downgrade() -> None:
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_event_type", "event",
        "type in ('stay_created','stay_ended','guest_relocated',"
        "'request_created','child_triaged','child_answered',"
        "'child_deferred','child_parked','child_closed','child_reopened',"
        "'staff_profile_created','staff_profile_updated',"
        "'staff_skills_set','roster_created','roster_updated',"
        "'assignment_created','assignment_updated','presence_changed',"
        "'work_order_created','work_order_pushed','work_order_broadcast',"
        "'work_order_accepted','work_order_in_progress',"
        "'work_order_completed','work_order_cancelled','child_routed',"
        "'child_done_pending_confirm','child_closed_confirmed',"
        "'child_reopened_by_guest','child_cancelled','escalation_opened',"
        "'escalation_resolved','recommendation_created','glitch_opened',"
        "'glitch_closed','cross_dept_notified','timer_fired',"
        "'sla_preset_created','sla_preset_updated',"
        "'escalation_ladder_created','escalation_ladder_updated')")

    op.drop_constraint("ck_ndr_mode", "no_dispatch_resolution",
                       type_="check")
    op.create_check_constraint(
        "ck_ndr_mode", "no_dispatch_resolution",
        "mode in ('grounded_answer','human_deferral')")

    op.drop_constraint("ck_rec_action", "recommendation", type_="check")
    op.create_check_constraint(
        "ck_rec_action", "recommendation",
        "action in ('reassign','broadcast','relocate','extend_sla',"
        "'approve','deny')")

    op.drop_table("event_reservation_mutated")
    op.drop_table("rec_apply_reservation_mutation")
    op.drop_column("child_sub_request", "requested_checkout")
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_migration_0006.py -q`
Expected: PASS. (Requires the Postgres from `backend/.env`; the inherited migration tests use the same.)

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/0006_conversation_answer_action.py backend/tests/spine/test_migration_0006.py
git commit -m "feat(migration): 0006 conv+answer-action (down_revision=0005_dispatch); additive"
```

---

### Task 7: LLM integration — `history` param + `requested_checkout` extraction

**Files:**
- Modify: `backend/conduit/shared/integrations/openai.py`
- Test: `backend/tests/spine/test_llm_history.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_llm_history.py
import inspect
from conduit.shared.integrations import openai as llm


def test_classify_and_ground_accept_history_kw():
    assert "history" in inspect.signature(llm.classify).parameters
    assert "history" in inspect.signature(llm.ground).parameters


def test_child_schema_has_requested_checkout():
    assert "requested_checkout" in llm._Child.model_fields
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_llm_history.py -q`
Expected: FAIL.

- [ ] **Step 3: Extend the integration**

In `backend/conduit/shared/integrations/openai.py`:

(a) add a field to `_Child`:

```python
class _Child(BaseModel):
    text: str
    issue_code: str | None
    fulfilment_mode: Literal["dispatch", "no_dispatch"] | None
    outcome: Literal["auto", "clarify", "flag", "no_dispatch"]
    is_problem_report: bool
    requested_checkout: str | None = None
```

(b) append to the `_SYS_CLASSIFY` string (before the final closing `)`), a new instruction sentence:

```python
    " If a child matches a reservation-mutation code and the guest is "
    "asking to change their checkout time/date, set requested_checkout to "
    "the requested checkout as an ISO-8601 timestamp resolved against the "
    "conversation; otherwise leave requested_checkout null."
```

(c) change `classify` and `ground` signatures + prompt assembly to thread `history` (extraction-only — prepended as CONVERSATION context, never altering the rule text):

```python
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
    except Exception as e:
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
        parsed = await _parse_ground(model, f"{q}\n\nCONTEXT\n{context}")
    except Exception as e:
        _record_failure()
        raise LLMUnavailable(str(e))
    _record_success()
    return parsed.model_dump()
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_llm_history.py -q`
Expected: PASS.

- [ ] **Step 5: Run the inherited LLM schema guard (regression)**

Run: `.venv/bin/pytest tests/spine/test_llm_schema_guard.py tests/spine/test_llm_bulkhead.py -q`
Expected: PASS (the new optional field defaults; bulkhead unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/integrations/openai.py backend/tests/spine/test_llm_history.py
git commit -m "feat(llm): history context + requested_checkout extraction (extraction-only)"
```

---

### Task 8: `triage.classify` — history passthrough + `requested_checkout` mapping (the D30 invariant)

**Files:**
- Modify: `backend/conduit/shared/domain/triage.py`
- Test: `backend/tests/spine/test_triage_history.py`

- [ ] **Step 1: Write the failing tests (incl. the signature D30 invariant)**

```python
# backend/tests/spine/test_triage_history.py
import datetime as dt
import pytest
from conduit.shared.domain import triage
from conduit.shared.integrations import openai as llm


CATALOG = [{"code": "LATE_CHECKOUT", "label": "Late checkout",
            "fulfilment_mode": "no_dispatch", "is_reservation_mutation": True}]


@pytest.mark.asyncio
async def test_history_does_not_change_outcome_only_extraction(monkeypatch):
    async def fake(text, catalog, history=""):
        return [{"text": text, "issue_code": "LATE_CHECKOUT",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": "2026-05-16T14:00:00+00:00"}]
    monkeypatch.setattr(llm, "classify", fake)

    no_hist = await triage.classify("till 2pm?", CATALOG)
    with_hist = await triage.classify("till 2pm?", CATALOG,
                                      history="guest: checkout?\nsystem: 11am")
    # Resolution A forces flag for a mutation code REGARDLESS of history:
    assert no_hist[0].outcome.value == "flag"
    assert with_hist[0].outcome.value == "flag"
    # Extraction carried through:
    assert with_hist[0].requested_checkout == dt.datetime(
        2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)


@pytest.mark.asyncio
async def test_bad_iso_is_conservative_none(monkeypatch):
    async def fake(text, catalog, history=""):
        return [{"text": text, "issue_code": "LATE_CHECKOUT",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False,
                 "requested_checkout": "not-a-date"}]
    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("x", CATALOG)
    assert out[0].requested_checkout is None   # never crash on LLM noise
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_triage_history.py -q`
Expected: FAIL (`classify` has no `history`; `TriagedChild` has no `requested_checkout`).

- [ ] **Step 3: Extend `triage.py`**

(a) add the field to the dataclass:

```python
@dataclass
class TriagedChild:
    text: str
    issue_code: str | None
    outcome: TriageOutcome
    uncategorized: bool = False
    is_problem_report: bool = False  # D43 → opens a Glitch
    requested_checkout: "dt.datetime | None" = None  # D24 extracted target
```

Add `import datetime as dt` to the imports.

(b) thread `history` and parse the extracted value (conservative — bad/empty ISO → None; the deterministic risk pass is **unchanged**):

```python
async def classify(text: str, catalog: list[dict],
                   history: str = "") -> list[TriagedChild]:
    raw = await llm.classify(text, catalog, history)   # extraction-only
    by_code = {c["code"]: c for c in catalog}
    result = []
    for item in raw:
        code = item.get("issue_code")
        cc = by_code.get(code) if code else None
        outcome = item["outcome"]
        if cc and cc.get("is_reservation_mutation"):    # Resolution A
            outcome = "flag"                            # raise only
        rc_raw = item.get("requested_checkout")
        rc = None
        if rc_raw:
            try:
                rc = dt.datetime.fromisoformat(rc_raw)
            except (ValueError, TypeError):
                rc = None                               # conservative
        result.append(TriagedChild(
            text=item["text"],
            issue_code=code if cc else None,
            outcome=TriageOutcome(outcome),
            uncategorized=cc is None,
            is_problem_report=bool(item.get("is_problem_report")),
            requested_checkout=rc,
        ))
    return result
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_triage_history.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run inherited triage tests (regression — back-compat default)**

Run: `.venv/bin/pytest tests/spine/test_triage.py -q`
Expected: PASS (the `history=""` default keeps every existing call byte-identical).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/domain/triage.py backend/tests/spine/test_triage_history.py
git commit -m "feat(triage): history passthrough + requested_checkout (D30 outcome unchanged)"
```

---

### Task 9: `grounding.ground` — history param

**Files:**
- Modify: `backend/conduit/shared/domain/grounding.py`
- Test: `backend/tests/spine/test_grounding_history.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_grounding_history.py
import inspect
import pytest
from conduit.shared.domain import grounding
from conduit.shared.integrations import openai as llm


def test_ground_accepts_history_kw():
    assert "history" in inspect.signature(grounding.ground).parameters


@pytest.mark.asyncio
async def test_history_is_forwarded(monkeypatch):
    seen = {}
    async def fake(q, ctx, history=""):
        seen["history"] = history
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "ok", "used_kb_ids": [], "used_fields": []}
    monkeypatch.setattr(llm, "ground", fake)
    await grounding.ground("q?", kb=[], facts={
        "room_label": "1", "section_label": "A", "check_in": "x",
        "check_out": "y", "stay_status": "active"}, history="H")
    assert seen["history"] == "H"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_grounding_history.py -q`
Expected: FAIL.

- [ ] **Step 3: Add the param**

In `backend/conduit/shared/domain/grounding.py`, change the signature and forward `history`:

```python
async def ground(question: str, *, kb: list[dict], facts: dict,
                 history: str = "") -> dict:
    lines = [f"- Reservation: room {facts['room_label']}, section "
             f"{facts['section_label']}, check_in {facts['check_in']}, "
             f"check_out {facts['check_out']}, status {facts['stay_status']}",
             "- Knowledge base:"]
    for e in kb:
        lines.append(f"[{e['id']}] {e['topic']}: {e['content']}")
    return await llm.ground(question, "\n".join(lines), history)
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_grounding_history.py tests/spine/test_grounding.py -q`
Expected: PASS (new + inherited grounding tests; default keeps back-compat).

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/grounding.py backend/tests/spine/test_grounding_history.py
git commit -m "feat(grounding): optional history context (extraction-only, back-compat)"
```

---

### Task 10: `recommendation.build` — `apply_reservation_mutation` branch

**Files:**
- Modify: `backend/conduit/shared/domain/recommendation.py`
- Test: `backend/tests/spine/test_recommendation.py` (extend)

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/spine/test_recommendation.py`:

```python
import datetime as dt


def test_triage_flag_reservation_mutation_yields_apply_action():
    when = dt.datetime(2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
    draft = build(trigger="triage_flag", child={"id": 1},
                  context={"verdict": "approve", "requested_checkout": when})
    assert draft.action == "apply_reservation_mutation"
    assert draft.params == {"field": "check_out", "requested_value": when}
    assert draft.rationale_text


def test_triage_flag_without_mutation_still_approve_deny():
    d1 = build(trigger="triage_flag", child={"id": 1},
               context={"verdict": "approve"})
    d2 = build(trigger="triage_flag", child={"id": 1},
               context={"verdict": "nope"})
    assert d1.action == "approve" and d2.action == "deny"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_recommendation.py -q`
Expected: FAIL (returns `approve`, not `apply_reservation_mutation`).

- [ ] **Step 3: Extend the pure builder**

In `backend/conduit/shared/domain/recommendation.py`:

(a) widen `_ACTIONS`:

```python
_ACTIONS = (
    "reassign", "broadcast", "relocate", "extend_sla", "approve", "deny",
    "apply_reservation_mutation",
)
```

(b) in `build`, replace the `else:  # triage_flag` block with the mutation-aware version (the action/params stay pure-Python deterministic; the LLM seam still only renders rationale):

```python
    else:  # triage_flag
        rc = context.get("requested_checkout")
        if rc is not None:
            # D24 answer↔action: a reservation-mutation flag carries the
            # already-extracted target (persisted at intake — the LLM is
            # NEVER in the auto-proceed path; D5/D30).
            action = "apply_reservation_mutation"
            params = {"field": "check_out", "requested_value": rc}
            template = (
                f"Guest requested a checkout change to {rc}; applying the "
                f"reservation mutation on approval."
            )
        else:
            verdict = context.get("verdict")
            if verdict == "approve":
                action = "approve"
                template = ("Triage flag reviewed; approving the flagged "
                            "request.")
            else:
                action = "deny"
                template = ("Triage flag reviewed; denying the flagged "
                            "request.")
            params = {}

    return RecommendationDraft(
        action=action,
        params=params,
        rationale_text=llm(template),
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_recommendation.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/recommendation.py backend/tests/spine/test_recommendation.py
git commit -m "feat(domain): recommendation.build apply_reservation_mutation (deterministic)"
```

---

### Task 11: Spine — `_REC_DETAIL`, `_resolved_action`, `_assemble_context`

**Files:**
- Modify: `backend/conduit/shared/engine/spine.py`
- Test: `backend/tests/spine/test_spine_mutation.py`

- [ ] **Step 1: Write failing tests (pure-ish: detail map + resolved action)**

```python
# backend/tests/spine/test_spine_mutation.py
import datetime as dt
from conduit.shared.engine import spine
from conduit.shared.models import RecApplyReservationMutation


def test_rec_detail_map_has_mutation():
    eid = __import__("uuid").uuid4()
    when = dt.datetime(2026, 5, 16, 14, 0, tzinfo=dt.timezone.utc)
    obj = spine._REC_DETAIL["apply_reservation_mutation"](
        eid, {"field": "check_out", "requested_value": when})
    assert isinstance(obj, RecApplyReservationMutation)
    assert obj.field == "check_out" and obj.requested_value == when
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_spine_mutation.py -q`
Expected: FAIL (`KeyError: 'apply_reservation_mutation'`).

- [ ] **Step 3: Extend `spine.py`**

(a) add to the model import line: `RecApplyReservationMutation`, `NoDispatchResolution` (append to the existing `from conduit.shared.models import (...)` tuple).

(b) add to the `_REC_DETAIL` dict (after the `"deny": ...` entry):

```python
    "apply_reservation_mutation": lambda eid, p: RecApplyReservationMutation(
        recommendation_escalation_id=eid,
        field=p["field"], requested_value=p["requested_value"]),
```

(c) in `_resolved_action`, inside the `if outcome in _STORED_REC_OUTCOMES:` block, add a branch before the final `return act, {}`:

```python
        if act == "apply_reservation_mutation":
            d = (await s.execute(sa.select(RecApplyReservationMutation).where(
                RecApplyReservationMutation.recommendation_escalation_id
                == esc.id))).scalar_one()
            return act, {"field": d.field,
                         "requested_value": d.requested_value}
```

(d) in `_assemble_context`, the `triage_flag` return (currently `return {"verdict": ctx.get("verdict")}`) becomes:

```python
    # triage_flag — the flag verdict (D5/D24) + the D24 extracted target
    # (persisted at intake on the child; the LLM is never re-invoked here).
    return {"verdict": ctx.get("verdict"),
            "requested_checkout": getattr(child, "requested_checkout", None)}
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_spine_mutation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/engine/spine.py backend/tests/spine/test_spine_mutation.py
git commit -m "feat(spine): wire apply_reservation_mutation through detail/resolve/context"
```

---

### Task 12: Writer `emit_reservation_mutated` + spine `_execute_action` apply branch

**Files:**
- Modify: `backend/conduit/shared/events/writer.py`
- Modify: `backend/conduit/shared/engine/spine.py` (`_execute_action`)
- Test: `backend/tests/spine/test_spine_mutation.py` (extend, DB-backed via the spine `db` fixture)

- [ ] **Step 1: Add the bespoke writer emitter**

In `backend/conduit/shared/events/writer.py`: add `EventReservationMutated` to the model import block, and append (bespoke shape — carries payload beyond a single FK, mirrors `emit_request_created`):

```python
async def emit_reservation_mutated(s, stay_id, field, old_value, new_value,
                                   actor_account_id=None) -> None:
    e = Event(type="reservation_mutated", actor_account_id=actor_account_id)
    s.add(e)
    await s.flush()
    s.add(EventReservationMutated(event_id=e.id, stay_id=stay_id,
                                  field=field, old_value=old_value,
                                  new_value=new_value))
```

- [ ] **Step 2: Add the executor branch**

In `backend/conduit/shared/engine/spine.py`, in `_execute_action`, add a branch (before the `relocate` comment / wherever the action chain ends — place it after the `extend_sla` block and before the relocate handling):

```python
    if act == "apply_reservation_mutation":
        # Resolve the Stay via the established child→Request→Stay chain
        # (engine-local read; Request/Stay already imported). Capture the
        # old value BEFORE the write for the append-only event.
        stay = (await s.execute(
            sa.select(Stay)
            .select_from(Request)
            .join(Stay, Stay.id == Request.stay_id)
            .where(Request.id == child.request_id)
        )).scalar_one()
        old = stay.check_out
        new = params["requested_value"]
        stay.check_out = new
        s.add(stay)
        await writer.emit_reservation_mutated(
            s, stay.id, params["field"], old, new, actor_id)
        # Closure-lite reuse (no new child states / endpoints): record the
        # outcome as a resolution and advance triaged→answered; the guest's
        # existing confirm endpoint then closes it (answered→closed).
        s.add(NoDispatchResolution(
            child_id=child.id, mode="reservation_mutation",
            answer_text=f"Your checkout is now {new:%Y-%m-%d %H:%M}."))
        await lifecycle.transition(s, child, "answered",
                                   actor_account_id=actor_id)
        return
```

- [ ] **Step 3: Write the failing DB-backed test**

Append to `backend/tests/spine/test_spine_mutation.py` (uses the spine `db` fixture + builders mirroring `test_spine.py`; if a helper to seed a child+escalation already exists in `tests/spine/test_spine.py`, import and reuse it rather than duplicating):

```python
import pytest


@pytest.mark.asyncio
async def test_execute_apply_mutation_changes_checkout_and_closes(db):
    """approve path: stay.check_out mutated, exactly one reservation_mutated
    event, child → answered (closure-lite), resolution recorded."""
    import datetime as dt
    import sqlalchemy as sa
    from conduit.shared.models import (Event, NoDispatchResolution, Stay,
                                       ChildSubRequest)
    # Reuse the spine test factory for a flagged reservation-mutation child
    # with an open escalation + stored RecApplyReservationMutation. See
    # tests/spine/test_spine.py helpers (seed_* ); construct: a Stay with a
    # known check_out, a Request→child (state 'triaged',
    # requested_checkout set), an Escalation(open, trigger='triage_flag'),
    # Recommendation(action='apply_reservation_mutation') + its detail.
    # Then call spine.apply_recommendation(db, esc, outcome="approved").
    # Assert:
    #   - Stay.check_out == the requested value
    #   - exactly one Event(type='reservation_mutated') with correct old/new
    #   - child.state == 'answered'
    #   - a NoDispatchResolution(mode='reservation_mutation') exists
    ...
```

> Replace the `...` with the concrete construction using the same factory helpers the existing `tests/spine/test_spine.py` uses for escalations (read that file first; it already builds Stay/Request/child/Escalation/Recommendation for the stall and servicer-raised cases — copy that scaffolding and set `trigger='triage_flag'`, `action='apply_reservation_mutation'`, child `requested_checkout`). Do not invent new factory APIs.

- [ ] **Step 4: Run, verify the executor test passes**

Run: `.venv/bin/pytest tests/spine/test_spine_mutation.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full inherited spine suite (regression — the executor is shared)**

Run: `.venv/bin/pytest tests/spine/test_spine.py tests/spine/test_supervisor_decisions.py tests/spine/test_engine.py -q`
Expected: PASS. The new branch is reached only for `act == "apply_reservation_mutation"`; every existing action path is byte-identical.

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/shared/events/writer.py backend/conduit/shared/engine/spine.py backend/tests/spine/test_spine_mutation.py
git commit -m "feat(spine): apply_reservation_mutation executor + emit_reservation_mutated"
```

---

### Task 13: Intake — history assembly, persist `requested_checkout`, mutation flag → spine

**Files:**
- Modify: `backend/conduit/guest/services/intake.py`
- Test: `backend/tests/spine/test_intake_history.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_intake_history.py
import pytest
from conduit.shared.integrations import openai as llm


@pytest.mark.asyncio
async def test_followup_mutation_opens_escalation_with_requested_checkout(
        db, fake_llm):
    """Seam: a prior grounded checkout answer + a 'till 2pm' follow-up →
    classify (history-aware) → mutation code force-flag → escalation opened
    with a Recommendation(action='apply_reservation_mutation')."""
    # Arrange a guest+active stay+section+a LATE_CHECKOUT issue code with
    # is_reservation_mutation=True and an active SLAPreset + EscalationLadder
    # (reuse the seeding helpers from tests/spine/test_intake_service.py /
    # test_supervisor_decisions.py — read them; do not invent).
    # fake_llm["classify"] returns one child {issue_code: LATE_CHECKOUT,
    # outcome: no_dispatch, requested_checkout: '2026-05-16T14:00:00+00:00'}.
    # Act: intake.submit_request(db, guest_actor, "can I get it till 2pm?")
    # Assert: an Escalation(trigger='triage_flag') exists for the child AND
    # a Recommendation(action='apply_reservation_mutation') AND
    # child.requested_checkout is the parsed datetime.
    ...
```

> Fill the `...` using the existing spine intake/decision seeding helpers (read `tests/spine/test_intake_service.py` and `tests/spine/test_supervisor_decisions.py` first — they already build guest/stay/section/issue-code/SLAPreset/EscalationLadder; reuse verbatim).

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_intake_history.py -q`
Expected: FAIL (no escalation opened — flag still parks).

- [ ] **Step 3: Modify `intake.submit_request`**

(a) add imports near the top:

```python
from conduit.shared.domain import conversation
from conduit.shared.engine import spine
from conduit.core.config import get_settings
```

(b) **Build the per-active-stay transcript and history string** just before `triaged = await triage.classify(text, catalog)`. Insert:

```python
    # --- Conversation window (extraction-only, Spec §7.1) ----------------
    # Reuse the EXACT read model the conversation view uses: prior requests
    # for this guest on the ACTIVE stay (request.stay_id == stay.id),
    # interleaved guest raw_text + system grounded answer_text, time-ordered.
    turns: list[conversation.Turn] = []
    prior = await rdal.list_requests_for_guest(s, actor.id)
    for pr in prior:
        if pr.stay_id != stay.id:
            continue                                   # per-stay isolation
        turns.append(conversation.Turn(role="guest", text=pr.raw_text))
        for c in await cdal.list_children_for_request(s, pr.id):
            res = await resdal.get_resolution(s, c.id)
            if res is not None and res.answer_text:
                turns.append(conversation.Turn(
                    role="system", text=res.answer_text))
    history = conversation.window(
        turns, limit=get_settings().conversation_window)
```

(c) thread `history` into classify and into the no-dispatch grounding call. Change:

```python
        triaged = await triage.classify(text, catalog)
```
to:
```python
        triaged = await triage.classify(text, catalog, history)
```

And pass `history` to no-dispatch resolution. In the loop, change the no-dispatch branch call from `await nodispatch.resolve(s, child, ambient, actor.id)` to `await nodispatch.resolve(s, child, ambient, actor.id, history=history)` — then add a matching `history: str = ""` keyword to `conduit/guest/services/nodispatch.resolve` and forward it into its `grounding.ground(..., history=history)` call. (Open `nodispatch.py`, add the optional kw, forward it; default keeps back-compat.)

(d) persist the extracted target on the child: in the `cdal.insert_child(...)` call, add `requested_checkout=t.requested_checkout,` to the kwargs (the `**f` passthrough stores it; no DAL change).

(e) wire the **reservation-mutation flag only** to the spine (non-mutation flags keep the existing park — minimal blast radius). Replace the final `else:` park block with:

```python
        else:
            if (t.outcome.value == "flag" and ic is not None
                    and ic.is_reservation_mutation):
                # D24 answer↔action seam: the mutation rides the spine's
                # generic FLAG trigger → decision queue (Spec §7.3).
                await spine.open_escalation(
                    s, child, "triage_flag",
                    actor_account_id=actor.id, verdict="approve")
                term = {"terminal": "flagged", "state": child.state}
            else:
                await writer.emit_child(s, "child_parked", child.id,
                                        actor.id)
                term = {"terminal": "logged"}
```

> `open_escalation` reads `child.requested_checkout` via `_assemble_context` (Task 11d) — the child row already has it (insert in step (d) + the `s.flush()` that precedes this branch). Do not pass it in `ctx`; the context assembler owns that read.

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_intake_history.py -q`
Expected: PASS.

- [ ] **Step 5: Run inherited intake regression**

Run: `.venv/bin/pytest tests/spine/test_intake_service.py tests/spine/test_guest_dispatch.py tests/spine/test_guest_api.py -q`
Expected: PASS — non-mutation flags still park (byte-identical); dispatch/no-dispatch/smalltalk branches unchanged; `history=""`-equivalent for first messages.

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/guest/services/intake.py backend/conduit/guest/services/nodispatch.py backend/tests/spine/test_intake_history.py
git commit -m "feat(intake): conversation window + persist requested_checkout + mutation flag→spine"
```

---

### Task 14: Guest read model — surface the mutation outcome (closure-lite reuse)

**Files:**
- Modify: `backend/conduit/guest/api/conversation.py` (`list_conversation`)
- Test: `backend/tests/spine/test_guest_mutation_card.py`

The `confirm` endpoint already works for `state=='answered'` + any resolution. Only the read needs to also recognise `reservation_mutation` mode so the card shows the answer text + closure prompt (currently it special-cases `grounded_answer`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/spine/test_guest_mutation_card.py
import pytest


@pytest.mark.asyncio
async def test_mutation_resolution_renders_answer_and_closure(db, client,
                                                              login):
    """A child in state 'answered' with a reservation_mutation resolution
    surfaces answer_text + closure_prompt via GET /guest/requests."""
    # Seed (reuse tests/spine/test_guest_api.py helpers): a guest + active
    # stay + a child(state='answered') + NoDispatchResolution(
    # mode='reservation_mutation', answer_text='Your checkout is now ...').
    # Then GET /api/guest/requests as that guest and assert the child dict
    # has answer == the answer_text and closure_prompt is True.
    ...
```

> Fill `...` from the existing `tests/spine/test_guest_api.py` patterns (read it; reuse its login/seed fixtures).

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/pytest tests/spine/test_guest_mutation_card.py -q`
Expected: FAIL (terminal/answer not surfaced for the new mode).

- [ ] **Step 3: Extend `list_conversation`**

In `backend/conduit/guest/api/conversation.py`, change the `terminal=` expression so it also recognises the mutation mode:

```python
                terminal=("answered" if c.state in ("answered", "closed")
                          and res and res.mode in (
                              "grounded_answer", "reservation_mutation")
                          else "logged"),
```

(`answer` and `closure_prompt` already derive from `res.answer_text` / `c.state == "answered"` and need no change.)

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/pytest tests/spine/test_guest_mutation_card.py -q`
Expected: PASS.

- [ ] **Step 5: Run inherited guest API regression**

Run: `.venv/bin/pytest tests/spine/test_guest_api.py -q`
Expected: PASS (grounded_answer rendering unchanged; the change is purely additive — one extra mode in the same tuple).

- [ ] **Step 6: Commit**

```bash
git add backend/conduit/guest/api/conversation.py backend/tests/spine/test_guest_mutation_card.py
git commit -m "feat(guest): surface reservation_mutation outcome on the conversation card"
```

---

### Task 15: Frontend — decision-form datetime variant (conditional on spine UI)

**Files:**
- Modify (if present): the supervisor decision-queue per-action form component in `frontend/` (the spine introduces it — sibling of the `rec_relocate` / `rec_extend_sla` variants)
- Test: manual (frontend has no unit harness in this repo path)

> The backend seam is fully testable headless (Tasks 12–14, 16). This task is **conditional**: the decision form is spine-owned and may not exist yet on the base branch.

- [ ] **Step 1: Locate the form**

```bash
cd /workspace/Conduit-conversation-answer-action/frontend
grep -rn "rec_relocate\|rec_extend_sla\|extend_seconds\|target_room_id" src/ | head
```

- [ ] **Step 2: Decide**

- If matches are found (the spine form exists): proceed to Step 3.
- If **no** matches (spine UI not yet built on the base branch): **skip the frontend** — record in the PR description "decision-form `apply_reservation_mutation` variant deferred: spine decision form not present on base; backend seam complete and headless-tested." Move to Task 16. (This is honest and expected given the spine is in flight; do not scaffold a speculative form.)

- [ ] **Step 3: Add the variant (only if Step 2 found the form)**

Following the exact sibling pattern the form already uses for `extend_sla` (a number field) / `relocate` (a select), add an `apply_reservation_mutation` case rendering a single datetime-local input bound to `requested_value`, submitted in the existing resolve payload shape (`{action, payload:{requested_value}}`). Match the file's existing component conventions verbatim — do not introduce new shadcn components (the spec mandates none).

- [ ] **Step 4: Typecheck/build**

Run: `npm run build`
Expected: PASS (typecheck + build clean).

- [ ] **Step 5: Commit (only if Step 3 ran)**

```bash
git add frontend/src
git commit -m "feat(ui): apply_reservation_mutation datetime variant in the decision form"
```

---

### Task 16: E2E seam sentinel

**Files:**
- Create: `backend/tests/spine/test_e2e_answer_action.py`

One scripted test that *is* the journey, with the approve path and the silent-auto-proceed path asserted to reach an identical end state (the spine's one-executor symmetry through a mutation).

- [ ] **Step 1: Write the sentinel test**

```python
# backend/tests/spine/test_e2e_answer_action.py
"""E2E: answer↔action seam (Spec §9.2). Approve path == silent
auto-proceed path (one-executor symmetry through a reservation mutation).
Time pinned via fire_at-past + synchronous engine tick (engine loop off).
"""
import pytest


@pytest.mark.asyncio
async def test_seam_approve_and_autoproceed_are_identical(db, client, login,
                                                          fake_llm):
    # Reuse the spine e2e scaffolding in tests/spine/test_e2e_journey.py:
    #   - seed supervisor + SLAPreset(P-tier) + EscalationLadder
    #   - seed guest + active stay (record original check_out) + section
    #   - seed a LATE_CHECKOUT issue_code: fulfilment_mode='no_dispatch',
    #     is_reservation_mutation=True, sla_preset_id set
    #
    # fake_llm["ground"] → a grounded checkout answer for "what time is
    #   checkout?"; fake_llm["classify"] → for the follow-up, one child
    #   {issue_code: LATE_CHECKOUT, outcome:'no_dispatch',
    #    requested_checkout:'<orig+3h ISO>'}.
    #
    # SCENARIO A (approve):
    #   POST /api/guest/requests "what time is checkout?"  → grounded answer
    #   POST /api/guest/requests "can I get it till 2pm?"  → escalation opens
    #   GET  /api/supervisor/decisions                     → the item present
    #   POST /api/supervisor/decisions/{id}/resolve {action:'approve'}
    #   assert Stay.check_out == requested; exactly ONE Event
    #     type='reservation_mutated' (old=orig,new=requested);
    #     child state 'answered'; NoDispatchResolution mode=
    #     'reservation_mutation'
    #   POST /api/guest/children/{cid}/confirm {helpful:true} → state 'closed'
    #
    # SCENARIO B (silence/auto-proceed) — fresh seed:
    #   same up to the escalation; DO NOT resolve. Make the supervisor_sla
    #   Timer due: set its fire_at into the past, then call the spine's
    #   synchronous test tick (engine.tick(session) — the helper
    #   tests/spine/test_engine.py uses; engine_enabled stays False).
    #   assert the SAME end state as A: Stay.check_out == requested, exactly
    #   one reservation_mutated event, child 'answered', resolution present,
    #   escalation resolved with resolved_by_account_id is None.
    #
    # FINAL: assert Scenario A and Scenario B produced byte-identical
    # (stay.check_out, child.state, resolution.mode, event count) — the
    # one-executor symmetry. Assert no extra Event rows (append-only: one
    # per transition). Construct everything with the existing helpers in
    # tests/spine/test_e2e_journey.py / test_engine.py — read them first;
    # do not invent factory or tick APIs.
    ...
```

> This is the slice's reason-to-exist test. Build it from the **existing** `tests/spine/test_e2e_journey.py` (seeding + HTTP flow) and `tests/spine/test_engine.py` (the `fire_at`-past + synchronous tick recipe). Reuse verbatim; invent nothing.

- [ ] **Step 2: Run, verify it passes**

Run: `.venv/bin/pytest tests/spine/test_e2e_answer_action.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/spine/test_e2e_answer_action.py
git commit -m "test(e2e): answer↔action seam — approve == auto-proceed symmetry"
```

---

### Task 17: Full suite + structural guards (zero-surface proof)

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite with the coverage gate**

Run: `.venv/bin/pytest -q`
Expected: PASS, `--cov-fail-under=90` satisfied, savepoint leak sentinel green.

- [ ] **Step 2: Assert zero API-surface drift**

Run: `.venv/bin/pytest tests/spine/test_structural_guards.py -q`
Expected: PASS. The route/contract snapshot must be **unchanged** (this slice added 0 endpoints — that is the positive proof). If the snapshot guard reports drift, you accidentally added/renamed a route — STOP and remove it; this slice must not touch the route surface.

- [ ] **Step 3: If anything is red**

Do not patch around it. Re-read the failing test and the spec section it maps to; the most likely culprits, in order: (a) a non-mutation flag accidentally routed to `open_escalation` (Task 13e gate wrong); (b) `down_revision` not `"0005_dispatch"`; (c) the executor branch placed where an earlier `return` shadows it; (d) `history` default lost on an inherited call. Fix the root cause, re-run from Step 1.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix: <root cause> (full suite + structural guards green)"
```

---

### Task 18: Push and open the PR

**Files:** none

- [ ] **Step 1: Final verification before push**

```bash
cd /workspace/Conduit-conversation-answer-action/backend
.venv/bin/pytest -q
cd /workspace/Conduit-conversation-answer-action && git status --short
```

Expected: full suite PASS; working tree clean (everything committed).

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/conversation-answer-action
```

- [ ] **Step 3: Open the PR (base = the spine branch)**

```bash
gh pr create \
  --base feat/dispatch-spine \
  --head feat/conversation-answer-action \
  --title "Conversation context + answer↔action seam" \
  --body "$(cat <<'EOF'
Stacks on feat/dispatch-spine (cannot target main until the spine merges).

## What
- Sliding 50-message conversation window (extraction-only) fed to
  classify/grounding. Deterministic risk rulebook unchanged (D5/D30).
- D24 answer↔action seam: a reservation follow-up force-flags through the
  spine's generic FLAG trigger and, on approve / edit / silent auto-proceed,
  the single executor mutates stay.check_out. Closure reuses closure-lite.

## Surface
- 0 new API endpoints; route/contract snapshot unchanged (asserted).
- Additive on the spine: 2 detail tables, 1 nullable child column, 3 CHECK
  widenings, 1 new recommendation action threaded through the existing
  single executor. Non-mutation flags keep byte-identical park behaviour.
- Migration 0006 (down_revision=0005_dispatch); round-trips clean.

## Tests
Full layered spine bench + the e2e seam sentinel (approve == auto-proceed
one-executor symmetry) green under savepoint isolation; --cov-fail-under=90.

Frontend decision-form variant: included if the spine decision form exists
on base; otherwise deferred (noted) — backend seam fully headless-tested.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr view --json url --jq .url
```

Expected: a PR URL targeting `feat/dispatch-spine`. Report it.

---

## Self-Review

**Spec coverage** (each spec §, the task that implements it):
- §2/§7.1 conversation window → Tasks 1, 2, 13(b)/(c)
- §2 extraction-only / D30 invariant → Tasks 7, 8 (signature invariant test), 9
- §4/§6 data model (2 detail tables, child column, 3 CHECK widenings, migration) → Tasks 3, 4, 5, 6
- §6/§7.3 recommendation action + builder → Task 10
- §7.3 spine threading (`_REC_DETAIL`/`_resolved_action`/`_assemble_context`) → Task 11
- §7.3 executor + event → Task 12
- §7.3 the seam wiring (flag→spine, mutation-only) + persist target → Task 13
- §8 zero-endpoint / closure-lite reuse / guest read → Tasks 13(e), 14, 17(step 2)
- §10 frontend one-variant (conditional) → Task 15
- §11/§12 bench + e2e sentinel + verification bar → Tasks 16, 17
- §3 docs-only-now / spine coupling / branch & PR base → Task 0, Task 18

**Placeholder scan:** the three `...`-bodied tests (Tasks 12, 13, 14, 16) are *deliberately* delegated to existing spine test factories with an explicit "read file X, reuse verbatim, invent nothing" instruction and exact assertions enumerated — because duplicating the spine's seed scaffolding here would drift from the in-flight base. Every production-code step contains complete, exact code. No `TODO`/`TBD`/"add error handling".

**Type/name consistency:** `Turn`/`window(turns, *, limit)` (Task 2) used identically in Task 13. `requested_checkout` (model col, `TriagedChild` field, context key, `child.requested_checkout` read) consistent across Tasks 5/8/11/13. `apply_reservation_mutation` action string + `{field, requested_value}` params identical across Tasks 3/10/11/12. `reservation_mutated` event type + `emit_reservation_mutated` signature identical Tasks 4/12. `down_revision="0005_dispatch"`, `revision="0006_conv_aa"` consistent Tasks 6. `mode="reservation_mutation"` consistent Tasks 5/12/14.
