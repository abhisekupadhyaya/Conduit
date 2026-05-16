# Dispatch & Escalation Spine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full dispatch journey + escalation spine + Glitch + cross-department notification + supervisor decision-queue/awareness + SLA/ladder configuration, single-intent, as one coherent branch/PR built in strictly ordered, individually-verified phases.

**Architecture:** Shared-owned spine (`shared/domain` pure + `shared/engine` runtime) with portals as thin guard+delegate surfaces. Pure `routing.select`, per-entity lifecycle machines + one orchestrator, AD5 durable DB timers driven in tests by `fire_at`-in-past + an explicit synchronous tick. One `apply_recommendation` executor invoked by both the supervisor resolve handler and the engine (silence ≡ approve, structural).

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2.0, Alembic, Postgres (required — `SKIP LOCKED` + physical invariants), pytest (`asyncio_mode=auto`, savepoint-rollback), Vite/React/TS/TanStack Query/shadcn.

**Source of truth:** `docs/superpowers/specs/2026-05-16-dispatch-spine-design.md` (§ references throughout) and the merged code patterns. Product decisions are cited as D-series, architecture as AD-series, exactly as the merged specs do — **do not introduce any new external document reference**.

---

## Operating constraints (read before Task 0)

- **Isolation:** all work happens in a **dedicated git worktree** created in Task 0. Never edit `/workspace/Conduit` working tree directly; it is the source only.
- **No new external references:** the spec already abstracts its sources as D-/AD-series. Plan, code, comments, commit messages, and the PR body must cite only D-/AD-series, `docs/datamodels/`, and prior Conduit specs — never any path outside the Conduit repo.
- **Subagents must be Opus.** When dispatching any subagent for a task, pass `model: "opus"` and name the **exact files** that task creates/modifies/tests (every task below lists them under **Files:** — copy that list verbatim into the subagent prompt). Never dispatch a Sonnet/Haiku subagent for any task in this plan.
- **House patterns (non-negotiable, copied from merged auth/stay-binding/no-dispatch/staffing):** fully async; `uuid` pk `default uuid.uuid4`; `DateTime(timezone=True)`; `text + CheckConstraint` (no PG enums, no jsonb); `created_at`/`updated_at` via `func.now()`/`onupdate`; CONFIG carries `status text+CHECK(active|disabled)` (disable-not-delete); DAL add-only / no flush / no commit; services guard + raise `core/exceptions` domain errors + emit exactly one append-only event via the merged `shared/events.writer` + `await s.flush()`; API handler `await s.commit()` at the edge, reads never commit; per-handler `require_roles(...)` server-side; **no `DELETE` anywhere → `405`, asserted**; one model per file registered in `shared/models/__init__.py` `__all__`.
- **Engine ordering:** every transition goes through `shared/domain/lifecycle.transition(...)` — the only writer path. Nothing writes `event`/`timer` directly except the writer/timers modules it calls.
- **TDD strictly:** write the failing test, run it red, minimal implement, run it green, commit. Postgres must be reachable (`postgres:5432`); SQLite is not acceptable for any task (physical CHECK/partial-unique/`SKIP LOCKED` invariants).

---

## File structure (decomposition lock)

```
backend/conduit/shared/models/      child_sub_request.py(modify) work_order.py timer.py
                                    escalation.py recommendation.py glitch.py
                                    cross_dept_notification.py sla_preset.py
                                    escalation_ladder.py issue_code.py(modify)
                                    event.py(modify) __init__.py(modify)
backend/conduit/shared/domain/      routing.py(implement) recommendation.py(new)
                                    lifecycle/__init__.py(orchestrator)
                                    lifecycle/child.py lifecycle/workorder.py
                                    lifecycle/escalation.py lifecycle/glitch.py
backend/conduit/shared/engine/      timers.py runner.py sweeper.py spine.py (all implement)
backend/conduit/shared/events/      writer.py(modify: + emit_* for new types)
backend/conduit/core/               deps.py(reuse staffing now() helper) config.py(verify flags)
backend/conduit/guest/              dal/requests.py services/conversation.py
                                    services/intake.py(modify) schemas/requests.py
                                    api/requests.py api/__init__.py(modify)
backend/conduit/servicer/           dal/tasks.py services/tasks.py schemas/tasks.py
                                    api/tasks.py api/__init__.py(modify)
backend/conduit/supervisor/         dal/{decisions,awareness,children,sla_presets,escalation_ladder}.py
                                    services/{decisions,override,setup}.py
                                    schemas/{decisions,awareness,setup}.py
                                    api/{decisions,override,setup}.py api/__init__.py(modify)
backend/migrations/versions/        0005_dispatch_spine.py
backend/tests/spine/                conftest.py(extend) test_migration_0005.py
                                    test_routing.py test_recommendation.py
                                    test_lifecycle_machines.py test_engine.py
                                    test_spine.py test_guest_dispatch.py
                                    test_servicer_tasks.py test_supervisor_decisions.py
                                    test_supervisor_setup.py test_awareness.py
                                    test_structural_guards.py test_e2e_dispatch.py
frontend/src/components/common/     countdown.tsx child-status-card.tsx(modify)
frontend/src/shell/guest/           hooks/use-conversation.ts(modify) pages/conversation.tsx(modify)
frontend/src/shell/servicer/        index.tsx(modify) hooks/use-tasks.ts pages/task-detail.tsx
frontend/src/shell/supervisor/      pages/{decisions,awareness,task-explorer,sla-presets,escalation-ladder}.tsx
                                    hooks/{use-decisions,use-awareness,use-children,use-sla-presets,use-escalation-ladder}.ts
                                    nav.tsx(modify)
frontend/src/App.tsx(modify)
```

---

## Phase 0 — Worktree, env, baseline

### Task 0: Create the isolated worktree, env, and verified-green baseline

**Files:**
- Create: git worktree `/workspace/Conduit-dispatch-spine` on branch `feat/dispatch-spine`
- Copy: `/workspace/Conduit/backend/.env` → worktree `backend/.env`; `/workspace/Conduit/frontend/.env` → worktree `frontend/.env`
- Create: worktree `backend/.venv` (cloned from `/workspace/Conduit/backend/.venv`)

- [ ] **Step 1: Create the worktree from the up-to-date base**

```bash
cd /workspace/Conduit
git fetch origin
git worktree add -b feat/dispatch-spine /workspace/Conduit-dispatch-spine origin/main
cd /workspace/Conduit-dispatch-spine
git log --oneline -3
```

Expected: worktree created; HEAD at latest `origin/main`.

> NOTE: this plan stacks on `0004_staffing` (`down_revision='0004_staffing'`). If staffing has **not** yet merged to `origin/main` at execution time, STOP and branch from the merged staffing commit instead (`git worktree add -b feat/dispatch-spine /workspace/Conduit-dispatch-spine <staffing-merge-sha>`). Confirm `backend/migrations/versions/0004_staffing.py` exists in the worktree before proceeding.

- [ ] **Step 2: Copy env files (never commit them — verify gitignored)**

```bash
cp /workspace/Conduit/backend/.env  /workspace/Conduit-dispatch-spine/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-dispatch-spine/frontend/.env
cd /workspace/Conduit-dispatch-spine
git check-ignore backend/.env frontend/.env
```

Expected: both paths echoed by `git check-ignore` (they are ignored). If either is NOT ignored, STOP — do not proceed; report it.

- [ ] **Step 3: Create the worktree venv from the existing one as source**

```bash
cd /workspace/Conduit-dispatch-spine/backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e ".[dev]" >/dev/null
.venv/bin/python --version
```

Expected: `Python 3.12.x`. (The source venv at `/workspace/Conduit/backend/.venv` is the reference for the exact dependency set; `pip install -e ".[dev]"` reproduces it from the locked `pyproject.toml`. If install fails offline, fall back to `cp -a /workspace/Conduit/backend/.venv /workspace/Conduit-dispatch-spine/backend/.venv` then `.venv/bin/pip install -e ".[dev]"`.)

- [ ] **Step 4: Verify a green baseline before writing a line**

Run:
```bash
cd /workspace/Conduit-dispatch-spine/backend
.venv/bin/alembic upgrade head
.venv/bin/pytest -q
```
Expected: migrations apply through `0004_staffing`; full suite **green**. If red, STOP — the baseline is broken; report, do not build on it.

- [ ] **Step 5: Frontend baseline**

Run:
```bash
cd /workspace/Conduit-dispatch-spine/frontend
npm install >/dev/null
npm run build
```
Expected: typecheck + production build pass.

- [ ] **Step 6: Commit the baseline marker (plan doc only — code unchanged)**

```bash
cd /workspace/Conduit-dispatch-spine
cp /workspace/Conduit/docs/superpowers/specs/2026-05-16-dispatch-spine-design.md docs/superpowers/specs/ 2>/dev/null || true
cp /workspace/Conduit/docs/superpowers/plans/2026-05-16-dispatch-spine.md docs/superpowers/plans/ 2>/dev/null || true
git add docs/superpowers/specs/2026-05-16-dispatch-spine-design.md docs/superpowers/plans/2026-05-16-dispatch-spine.md
git commit -m "docs: dispatch & spine slice — design + plan"
```

Expected: one docs-only commit on `feat/dispatch-spine`.

---

## Phase A — Data model & migration 0005

> All Phase A models follow the merged `issue_code.py`/`staff_profile.py` idiom verbatim. One model per file; register in `shared/models/__init__.py` `__all__` in this firm order appended after the existing entries: `sla_preset → escalation_ladder → work_order → timer → escalation → recommendation → rec_reassign → rec_relocate → rec_extend_sla → rec_approve → rec_deny → rec_broadcast → glitch → cross_dept_notification` then the new event-detail classes. Spec §6 is the column contract; copy it exactly.

### Task A1: CONFIG models — `sla_preset`, `escalation_ladder`

**Files:**
- Create: `backend/conduit/shared/models/sla_preset.py`
- Create: `backend/conduit/shared/models/escalation_ladder.py`
- Modify: `backend/conduit/shared/models/__init__.py` (import + `__all__`)
- Test: `backend/tests/spine/test_migration_0005.py` (created here, grown across Phase A)

- [ ] **Step 1: Write the failing model-shape test**

```python
# backend/tests/spine/test_migration_0005.py
import pytest
from sqlalchemy import inspect
from conduit.shared.models import SLAPreset, EscalationLadder

def test_sla_preset_columns():
    cols = {c.name for c in inspect(SLAPreset).columns}
    assert cols == {"id","property_id","tier","accept_window_seconds",
                    "fulfilment_sla_seconds","supervisor_sla_seconds",
                    "status","created_at","updated_at"}

def test_escalation_ladder_columns():
    cols = {c.name for c in inspect(EscalationLadder).columns}
    assert cols == {"id","property_id","duty_manager_account_id",
                    "n_cycle_bound","status","created_at","updated_at"}
```

- [ ] **Step 2: Run red**

Run: `.venv/bin/pytest tests/spine/test_migration_0005.py -q`
Expected: FAIL — `ImportError: cannot import name 'SLAPreset'`.

- [ ] **Step 3: Implement the two models (copy the `issue_code.py` idiom)**

```python
# backend/conduit/shared/models/sla_preset.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class SLAPreset(Base):
    __tablename__ = "sla_preset"
    __table_args__ = (
        CheckConstraint("tier in ('P1','P2','P3','P4')", name="ck_sla_tier"),
        CheckConstraint("status in ('active','disabled')", name="ck_sla_status"),
        Index("uq_sla_active_tier", "property_id", "tier",
              unique=True, postgresql_where="status = 'active'"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("property.id"), nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    accept_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfilment_sla_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    supervisor_sla_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

```python
# backend/conduit/shared/models/escalation_ladder.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class EscalationLadder(Base):
    __tablename__ = "escalation_ladder"
    __table_args__ = (
        CheckConstraint("status in ('active','disabled')", name="ck_ladder_status"),
        CheckConstraint("n_cycle_bound > 0", name="ck_ladder_nbound"),
        Index("uq_ladder_active_property", "property_id",
              unique=True, postgresql_where="status = 'active'"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("property.id"), nullable=False)
    duty_manager_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=False)
    n_cycle_bound: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

Modify `backend/conduit/shared/models/__init__.py`: add `from conduit.shared.models.sla_preset import SLAPreset` and `from conduit.shared.models.escalation_ladder import EscalationLadder`, append both names to `__all__` (after the last existing staffing entry, before any test-only ordering).

- [ ] **Step 4: Run green**

Run: `.venv/bin/pytest tests/spine/test_migration_0005.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/sla_preset.py backend/conduit/shared/models/escalation_ladder.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): SLAPreset + EscalationLadder CONFIG (D15/D21)"
```

### Task A2: SPINE models — `work_order`, `timer`, `escalation`

**Files:**
- Create: `backend/conduit/shared/models/work_order.py`, `timer.py`, `escalation.py`
- Modify: `backend/conduit/shared/models/__init__.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Append failing column tests**

```python
# add to backend/tests/spine/test_migration_0005.py
from conduit.shared.models import WorkOrder, Timer, Escalation

def test_work_order_columns():
    cols = {c.name for c in inspect(WorkOrder).columns}
    assert cols == {"id","child_id","kind","routing_model","assigned_servicer_id",
                    "accountable_owner_id","section_id","priority_tier",
                    "queue_position","state","completion_notes","created_at","updated_at"}

def test_timer_columns():
    cols = {c.name for c in inspect(Timer).columns}
    assert cols == {"id","type","child_id","work_order_id","escalation_id",
                    "fire_at","state","cycle","created_at"}

def test_escalation_columns():
    cols = {c.name for c in inspect(Escalation).columns}
    assert cols == {"id","child_id","trigger","state","cycle_count",
                    "raised_by_account_id","resolved_by_account_id",
                    "created_at","resolved_at"}
```

- [ ] **Step 2: Run red**

Run: `.venv/bin/pytest tests/spine/test_migration_0005.py -q`
Expected: FAIL — import error for `WorkOrder`.

- [ ] **Step 3: Implement (spec §6 column contract verbatim)**

```python
# backend/conduit/shared/models/work_order.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class WorkOrder(Base):
    __tablename__ = "work_order"
    __table_args__ = (
        CheckConstraint("kind in ('dispatch','human_concierge_answer')", name="ck_wo_kind"),
        CheckConstraint("routing_model in ('section_pooled','skill_matched')", name="ck_wo_model"),
        CheckConstraint("priority_tier in ('P1','P2','P3','P4')", name="ck_wo_tier"),
        CheckConstraint("state in ('created','pushed','broadcast','accepted',"
                        "'in_progress','completed','cancelled')", name="ck_wo_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    routing_model: Mapped[str] = mapped_column(String, nullable=False)
    assigned_servicer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    accountable_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("section.id"), nullable=True)
    priority_tier: Mapped[str] = mapped_column(String, nullable=False)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="created")
    completion_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

```python
# backend/conduit/shared/models/timer.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class Timer(Base):
    __tablename__ = "timer"
    __table_args__ = (
        CheckConstraint("type in ('accept_window','fulfilment_sla',"
                        "'supervisor_sla','backstop_cycle')", name="ck_timer_type"),
        CheckConstraint("state in ('pending','fired','cancelled')", name="ck_timer_state"),
        CheckConstraint(
            "(child_id is not null)::int + (work_order_id is not null)::int "
            "+ (escalation_id is not null)::int = 1", name="ck_timer_one_subject"),
        Index("ix_timer_state_fire_at", "state", "fire_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=True)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=True)
    escalation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("escalation.id"), nullable=True)
    fire_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")
    cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

```python
# backend/conduit/shared/models/escalation.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class Escalation(Base):
    __tablename__ = "escalation"
    __table_args__ = (
        CheckConstraint("trigger in ('triage_flag','stall','servicer_raised')", name="ck_esc_trigger"),
        CheckConstraint("state in ('open','approved','edited','overridden',"
                        "'auto_proceeded','hard_escalated')", name="ck_esc_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False)
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="open")
    cycle_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    raised_by_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    resolved_by_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Register all three in `__init__.py` / `__all__`.

- [ ] **Step 4: Run green**

Run: `.venv/bin/pytest tests/spine/test_migration_0005.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/work_order.py backend/conduit/shared/models/timer.py backend/conduit/shared/models/escalation.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): WorkOrder + Timer(typed-FK,one-subject CHECK) + Escalation"
```

### Task A3: `recommendation` base + per-action detail tables

**Files:**
- Create: `backend/conduit/shared/models/recommendation.py` (base + `RecReassign`/`RecRelocate`/`RecExtendSla`/`RecApprove`/`RecDeny`/`RecBroadcast` in one file — they are a single cohesive 1:1 family, like the event-detail family in `event.py`)
- Modify: `__init__.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Failing test**

```python
# add to test_migration_0005.py
from conduit.shared.models import (Recommendation, RecReassign, RecRelocate,
    RecExtendSla, RecApprove, RecDeny, RecBroadcast)

def test_recommendation_family():
    base = {c.name for c in inspect(Recommendation).columns}
    assert base == {"escalation_id","action","rationale_text","created_at"}
    assert {c.name for c in inspect(RecReassign).columns} == {"recommendation_escalation_id","target_account_id"}
    assert {c.name for c in inspect(RecRelocate).columns} == {"recommendation_escalation_id","target_room_id"}
    assert {c.name for c in inspect(RecExtendSla).columns} == {"recommendation_escalation_id","extend_seconds"}
    for m in (RecApprove, RecDeny, RecBroadcast):
        assert {c.name for c in inspect(m).columns} == {"recommendation_escalation_id"}
```

- [ ] **Step 2: Run red** — `.venv/bin/pytest tests/spine/test_migration_0005.py -q` → FAIL import.

- [ ] **Step 3: Implement**

```python
# backend/conduit/shared/models/recommendation.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class Recommendation(Base):
    __tablename__ = "recommendation"
    __table_args__ = (
        CheckConstraint("action in ('reassign','broadcast','relocate',"
                        "'extend_sla','approve','deny')", name="ck_rec_action"),
    )
    escalation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("escalation.id"), primary_key=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    rationale_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class _RecDetail(Base):
    __abstract__ = True
    recommendation_escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendation.escalation_id"), primary_key=True)

class RecReassign(_RecDetail):
    __tablename__ = "rec_reassign"
    target_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=False)

class RecRelocate(_RecDetail):
    __tablename__ = "rec_relocate"
    target_room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)

class RecExtendSla(_RecDetail):
    __tablename__ = "rec_extend_sla"
    extend_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

class RecApprove(_RecDetail):
    __tablename__ = "rec_approve"

class RecDeny(_RecDetail):
    __tablename__ = "rec_deny"

class RecBroadcast(_RecDetail):
    __tablename__ = "rec_broadcast"
```

Register every class in `__init__.py`/`__all__`.

- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/recommendation.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): Recommendation base + per-action detail tables"
```

### Task A4: `glitch`, `cross_dept_notification`

**Files:**
- Create: `backend/conduit/shared/models/glitch.py`, `cross_dept_notification.py`
- Modify: `__init__.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Failing test**

```python
# add to test_migration_0005.py
from conduit.shared.models import Glitch, CrossDeptNotification

def test_glitch_columns():
    assert {c.name for c in inspect(Glitch).columns} == {"id","child_id","state",
        "opened_from","recovery_owed","recovery_cost","created_at","closed_at"}

def test_cross_dept_columns():
    assert {c.name for c in inspect(CrossDeptNotification).columns} == {"id",
        "source_work_order_id","target_department","child_id","reason","state","created_at"}
```

- [ ] **Step 2: Run red** → FAIL import.
- [ ] **Step 3: Implement**

```python
# backend/conduit/shared/models/glitch.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Boolean, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class Glitch(Base):
    __tablename__ = "glitch"
    __table_args__ = (
        CheckConstraint("state in ('open','held_open','auto_closed','closed')", name="ck_glitch_state"),
        CheckConstraint("opened_from in ('problem_report','dispute')", name="ck_glitch_origin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="open")
    opened_from: Mapped[str] = mapped_column(String, nullable=False)
    recovery_owed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    recovery_cost: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

```python
# backend/conduit/shared/models/cross_dept_notification.py
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

class CrossDeptNotification(Base):
    __tablename__ = "cross_dept_notification"
    __table_args__ = (
        CheckConstraint("target_department in ('housekeeping','engineering',"
            "'room_service','concierge','front_desk','runner')", name="ck_xdn_dept"),
        CheckConstraint("state in ('open','acknowledged')", name="ck_xdn_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_work_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("work_order.id"), nullable=False)
    target_department: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="open")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

Register both.

- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/glitch.py backend/conduit/shared/models/cross_dept_notification.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): Glitch (D43/D44/D19) + CrossDeptNotification (D14)"
```

### Task A5: Additive `child_sub_request` columns + state CHECK widen; `issue_code.sla_preset_id`

**Files:**
- Modify: `backend/conduit/shared/models/child_sub_request.py`
- Modify: `backend/conduit/shared/models/issue_code.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Failing test**

```python
# add to test_migration_0005.py
from conduit.shared.models import ChildSubRequest, IssueCode

def test_child_additive_columns():
    cols = {c.name for c in inspect(ChildSubRequest).columns}
    assert {"priority_tier","closure","revised_eta","predecessor_child_id"} <= cols

def test_child_state_check_widened():
    ck = next(c for c in ChildSubRequest.__table__.constraints
              if getattr(c, "name", "") == "ck_child_state")
    txt = str(ck.sqltext)
    for s in ("routing","pushed","broadcast","accepted","in_progress",
              "done_pending_confirm","cancelled"):
        assert s in txt

def test_issue_code_sla_fk():
    assert "sla_preset_id" in {c.name for c in inspect(IssueCode).columns}
```

- [ ] **Step 2: Run red** → FAIL.

- [ ] **Step 3: Implement — add the columns and widen the CHECK**

In `child_sub_request.py`: replace the `ck_child_state` CheckConstraint string with:
```python
CheckConstraint(
    "state in ('intake','triaged','clarifying','routing','pushed','broadcast',"
    "'accepted','in_progress','done_pending_confirm','answered',"
    "'concierge_queue','closed','reopened','cancelled')", name="ck_child_state"),
```
Add a `ck_child_closure` constraint `"closure is null or closure in ('pending','confirmed','reopened','aging')"` and the four columns:
```python
priority_tier: Mapped[str | None] = mapped_column(String, nullable=True)
closure: Mapped[str | None] = mapped_column(String, nullable=True)
revised_eta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
predecessor_child_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=True)
```
(Add `CheckConstraint("priority_tier is null or priority_tier in ('P1','P2','P3','P4')", name="ck_child_tier")`.)

In `issue_code.py`: add
```python
sla_preset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sla_preset.id"), nullable=True)
```

- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/child_sub_request.py backend/conduit/shared/models/issue_code.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): child dispatch cols + widened state CHECK; issue_code.sla_preset_id (additive)"
```

### Task A6: Extend the `event` taxonomy + detail tables

**Files:**
- Modify: `backend/conduit/shared/models/event.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Failing test**

```python
# add to test_migration_0005.py
from conduit.shared.models import Event

def test_event_type_extended():
    ck = next(c for c in Event.__table__.constraints
              if getattr(c, "name", "") == "ck_event_type")
    txt = str(ck.sqltext)
    for t in ("work_order_created","work_order_completed","child_routed",
              "child_closed_confirmed","escalation_opened","escalation_resolved",
              "recommendation_created","glitch_opened","glitch_closed",
              "cross_dept_notified","timer_fired","sla_preset_created",
              "escalation_ladder_created"):
        assert t in txt
```

- [ ] **Step 2: Run red** → FAIL.

- [ ] **Step 3: Implement** — extend the `ck_event_type` CHECK string in `event.py` additively with the full new-type list from spec §6 "Event taxonomy", and add one thin detail class per type following the existing `_ChildEvent`/`EventRequestCreated` idiom (e.g. `EventWorkOrderCreated{event_id pk fk, work_order_id fk}`, `EventEscalationOpened{event_id pk fk, escalation_id fk}`, `EventGlitchOpened{event_id pk fk, glitch_id fk}`, `EventTimerFired{event_id pk fk, timer_id fk}`, `EventCrossDeptNotified{event_id pk fk, cross_dept_notification_id fk}`, `EventSlaPresetCreated{event_id pk fk, sla_preset_id fk}`, `EventEscalationLadderCreated{event_id pk fk, escalation_ladder_id fk}`, `EventChildRouted/EventChildClosedConfirmed/EventChildCancelled` reuse `_ChildEvent`). Register every new detail class in `__init__.py`/`__all__`.

- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/models/event.py backend/conduit/shared/models/__init__.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(model): extend event taxonomy + detail tables (additive)"
```

### Task A7: Migration `0005_dispatch_spine` + physical-invariant tests

**Files:**
- Create: `backend/migrations/versions/0005_dispatch_spine.py`
- Test: `backend/tests/spine/test_migration_0005.py`

- [ ] **Step 1: Failing migration + invariant tests**

```python
# add to test_migration_0005.py
import sqlalchemy as sa
from alembic.config import Config
from alembic import command

@pytest.mark.asyncio
async def test_migration_round_trip(db):
    # db fixture is at head already (conftest builds head). Assert tables exist:
    insp = await db.run_sync(lambda s: sa.inspect(s.bind))
    names = set(await db.run_sync(lambda s: sa.inspect(s.bind).get_table_names()))
    for t in ("work_order","timer","escalation","recommendation","rec_reassign",
              "glitch","cross_dept_notification","sla_preset","escalation_ladder"):
        assert t in names

@pytest.mark.asyncio
async def test_timer_one_subject_check(db):
    from conduit.shared.models import Timer
    import datetime as dt, uuid
    bad = Timer(type="accept_window", fire_at=dt.datetime.now(dt.UTC))  # zero subjects
    db.add(bad)
    with pytest.raises(Exception):
        await db.flush()
```

(Add analogous negative+positive tests: 2nd `work_order.child_id` rejected; 2nd `glitch.child_id` rejected; 2nd active `sla_preset` for `(property,tier)` rejected while a disabled one is allowed; `down_revision == '0004_staffing'`.)

- [ ] **Step 2: Run red** → FAIL (no `0005`; conftest head build errors).

- [ ] **Step 3: Author the migration**

Generate then hand-verify:
```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "0005 dispatch spine"
```
Rename the file to `0005_dispatch_spine.py`, set `down_revision = "0004_staffing"`, `revision = "0005_dispatch"`. Hand-audit the autogenerate: it must `create_table` the 9 new tables + recommendation/event detail tables, `create_index` the two partial-unique indexes (`postgresql_where`) and `ix_timer_state_fire_at`, `add_column` the four child columns + `issue_code.sla_preset_id`, and `alter` the `ck_child_state` / `ck_event_type` CHECKs (drop+recreate constraint in both `upgrade` and `downgrade`). Remove any spurious diffs. Ensure `downgrade()` exactly reverses (drop new tables/cols, restore the prior CHECK strings verbatim).

- [ ] **Step 4: Run green**

Run:
```bash
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
.venv/bin/pytest tests/spine/test_migration_0005.py -q
```
Expected: clean round-trip; all migration tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/0005_dispatch_spine.py backend/tests/spine/test_migration_0005.py
git commit -m "feat(migration): 0005_dispatch_spine (down_revision=0004_staffing); physical invariants"
```

### Task A8: Phase A checkpoint — full suite green

- [ ] **Step 1:** Run `cd backend && .venv/bin/pytest -q`. Expected: entire suite green (new model/migration tests + all inherited). If the inherited contract snapshot is red, that is expected drift from new tables only if routes changed — at Phase A there are **no new routes**, so a red snapshot here means an unintended change; investigate, do not regenerate yet.
- [ ] **Step 2:** Commit nothing (verification only). Record: "Phase A complete — data model + migration green."

---

## Phase B — Timer engine (AD5)

> Implements `shared/engine/timers.py`, `runner.py`, `sweeper.py`. The engine has **engine-local data access** (its own background `AsyncSession`); it does **not** import any portal DAL. Time source is DB `now()`. Tests: `s.engine_enabled=False` (verify the flag exists in `core/config.py`; staffing relies on it), `fire_at` set into the past, explicit synchronous `engine.tick(session)`.

### Task B1: `timers.arm` / `timers.cancel_for`

**Files:**
- Modify: `backend/conduit/shared/engine/timers.py`
- Test: `backend/tests/spine/test_engine.py` (create)

- [ ] **Step 1: Failing test**

```python
# backend/tests/spine/test_engine.py
import datetime as dt, uuid, pytest
from conduit.shared.engine import timers
from conduit.shared.models import Timer, ChildSubRequest, Request
from sqlalchemy import select

async def _child(db):
    r = Request(guest_account_id=uuid.uuid4(), stay_id=uuid.uuid4(),
                raw_text="x", channel="text")
    # use real fixtures in practice; here assume helper builds a valid child
    ...

@pytest.mark.asyncio
async def test_arm_writes_pending_timer(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW,
                     fire_at=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15))
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert len(rows) == 1 and rows[0].state == "pending" and rows[0].type == "accept_window"

@pytest.mark.asyncio
async def test_cancel_for_marks_cancelled(db, make_child):
    child = await make_child(db)
    await timers.arm(db, "child_id", child.id, timers.TimerType.FULFILMENT_SLA,
                     fire_at=dt.datetime.now(dt.UTC))
    await db.flush()
    await timers.cancel_for(db, "child_id", child.id)
    await db.flush()
    rows = (await db.execute(select(Timer).where(Timer.child_id == child.id))).scalars().all()
    assert all(r.state == "cancelled" for r in rows)
```

(Add `make_child` to `tests/spine/conftest.py` in Task B0-prep: a fixture creating a valid `Request`+`ChildSubRequest` via real models; reuse merged factory helpers if present.)

- [ ] **Step 2: Run red** → FAIL (`arm` raises `NotImplementedError`).

- [ ] **Step 3: Implement** (replace the stubs; map `subject_kind` string → the typed FK column)

```python
# backend/conduit/shared/engine/timers.py  (replace bodies)
import datetime as dt
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models import Timer

_SUBJECT = {"child_id": "child_id", "work_order_id": "work_order_id",
            "escalation_id": "escalation_id"}

async def arm(s: AsyncSession, subject_kind: str, subject_id: uuid.UUID,
              timer_type: "TimerType", *, fire_at: dt.datetime,
              cycle: int | None = None) -> Timer:
    col = _SUBJECT[subject_kind]
    t = Timer(type=timer_type.value, fire_at=fire_at, cycle=cycle,
              **{col: subject_id})
    s.add(t)
    return t

async def cancel_for(s: AsyncSession, subject_kind: str, subject_id: uuid.UUID) -> None:
    col = _SUBJECT[subject_kind]
    await s.execute(update(Timer)
        .where(getattr(Timer, col) == subject_id, Timer.state == "pending")
        .values(state="cancelled"))
```

Keep the `TimerType` enum already defined in the file.

- [ ] **Step 4: Run green** — `.venv/bin/pytest tests/spine/test_engine.py -q` PASS (2).
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/engine/timers.py backend/tests/spine/test_engine.py backend/tests/spine/conftest.py
git commit -m "feat(engine): timers.arm / cancel_for (typed-subject)"
```

### Task B2: `runner.tick` — claim & fire (SKIP LOCKED), `engine_enabled` off in tests

**Files:**
- Modify: `backend/conduit/shared/engine/runner.py`
- Modify: `backend/conduit/core/config.py` (only if `engine_enabled`/`engine_poll_seconds` absent — verify first; staffing referenced them, expect present)
- Test: `backend/tests/spine/test_engine.py`

- [ ] **Step 1: Failing test**

```python
# add to test_engine.py
from conduit.shared.engine import runner

@pytest.mark.asyncio
async def test_tick_fires_only_due_pending(db, make_child):
    child = await make_child(db)
    from conduit.shared.engine import timers
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    await timers.arm(db, "child_id", child.id, timers.TimerType.ACCEPT_WINDOW, fire_at=past)
    await timers.arm(db, "child_id", child.id, timers.TimerType.FULFILMENT_SLA, fire_at=future)
    await db.flush()
    fired = await runner.tick(db)
    assert fired == 1   # only the past one
```

- [ ] **Step 2: Run red** → FAIL (no `tick`).

- [ ] **Step 3: Implement** the synchronous, testable claim-and-fire used by both the loop and tests:

```python
# backend/conduit/shared/engine/runner.py  (add; keep run_engine wrapping it)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def tick(s: AsyncSession, *, limit: int = 50) -> int:
    rows = (await s.execute(text(
        "SELECT id FROM timer WHERE state='pending' AND fire_at <= now() "
        "ORDER BY fire_at FOR UPDATE SKIP LOCKED LIMIT :k"), {"k": limit})).all()
    n = 0
    for (timer_id,) in rows:
        try:
            await _fire_one(s, timer_id)   # dispatches to spine per Timer.type
            n += 1
        except Exception:
            await _record_failed(s, timer_id)   # failed_transitions + log; never silent
    return n
```

`_fire_one` loads the `Timer`, branches on `type`: `accept_window`/`fulfilment_sla` → `spine.on_stall(s, timer)`; `supervisor_sla` → `spine.apply_recommendation(s, escalation, outcome="auto_proceeded")`; `backstop_cycle` → `spine.hard_escalate(...)`; then `timer.state='fired'` + `writer.emit_timer_fired(s, timer.id, None)`. `_record_failed` inserts a `failed_transitions` row (create the trivial model in this task — `id, timer_id, error, at`) and logs `log.exception`. `run_engine`'s loop body becomes `await tick(s)` inside a fresh background session when `s.engine_enabled`. Leave `run_engine` short-circuit on `not s.engine_enabled` intact (the test seam).

- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/engine/runner.py backend/tests/spine/test_engine.py backend/conduit/shared/models/__init__.py
git commit -m "feat(engine): runner.tick claim&fire (SKIP LOCKED) + failed_transitions"
```

### Task B3: `sweeper.sweep` — overdue/orphan watchdog

**Files:**
- Modify: `backend/conduit/shared/engine/sweeper.py`
- Test: `backend/tests/spine/test_engine.py`

- [ ] **Step 1: Failing test** — arm a timer with `fire_at` 1h in the past, do **not** tick, assert `sweep(db)` returns the overdue count ≥1 and logs/metrics a non-zero "age of oldest unfired timer".
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** `sweep(s)`: `SELECT count(*), min(fire_at) FROM timer WHERE state='pending' AND fire_at < now()`; emit the metric via the existing logging/metric path; return the count. No state mutation (watchdog only).
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/engine/sweeper.py backend/tests/spine/test_engine.py
git commit -m "feat(engine): sweeper.sweep overdue/orphan watchdog (AD5)"
```

---

## Phase C — Pure domain (routing, recommendation, lifecycle machines + orchestrator)

> All Phase C `shared/domain` modules are **pure: no DB, no I/O**. They take already-fetched rows + explicit `now`. This is the `availability.py`/`triage.py`/`grounding.py` precedent. Exhaustive truth-table tests, no fixtures needed beyond plain dataclasses/model instances.

### Task C1: `routing.select` (D12 / D18), replacing the side-effecting stub

**Files:**
- Modify: `backend/conduit/shared/domain/routing.py`
- Test: `backend/tests/spine/test_routing.py` (create)

- [ ] **Step 1: Failing exhaustive test** — cover: D12 owner available → owner selected as both assignee+accountable; D12 owner busy → broadcast plan with in-zone available pool, accountable=owner; D18 skill match → least-loaded; D18 load tie → P1 preempts lower tier; no eligible candidate → `Selection(flag=True)`. Use plain inputs (the staffing `availability.effective_available` is imported and called; feed candidates whose profiles/assignments make it return the desired booleans, with explicit `now`).

```python
# backend/tests/spine/test_routing.py — representative cases
from conduit.shared.domain import routing
def test_d12_owner_available_selected(): ...
def test_d12_owner_busy_broadcasts_pool_owner_stays_accountable(): ...
def test_d18_skill_match_least_loaded(): ...
def test_d18_load_tie_p1_preempts(): ...
def test_no_candidate_flags(): ...
```

(Write each with concrete constructed inputs and asserted `Selection` fields — no placeholder bodies.)

- [ ] **Step 2: Run red** → FAIL (`route` raises `NotImplementedError`; `select` undefined).
- [ ] **Step 3: Implement** a pure `select(*, model: RoutingModel, candidates, now) -> Selection` where `Selection` is a frozen dataclass `{assigned_id, accountable_id, broadcast_pool: list[id], section_id, queue_position, flag: bool, flag_reason: str|None}`. Internally call `availability.effective_available(profile, assignments, now)` per candidate. Remove/replace the stub `route(...)`. D12 and D18 branches exactly per spec §7.1.
- [ ] **Step 4: Run green** — PASS (all cases).
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/routing.py backend/tests/spine/test_routing.py
git commit -m "feat(domain): pure routing.select (D12/D18); stub route() replaced"
```

### Task C2: `recommendation.build` — deterministic action + templated rationale

**Files:**
- Create: `backend/conduit/shared/domain/recommendation.py`
- Test: `backend/tests/spine/test_recommendation.py` (create)

- [ ] **Step 1: Failing test** — per trigger: `stall` → `("reassign", {target_account_id}, "<templated>")` (or `broadcast` when no single target); `servicer_raised` "can't fix" → `("relocate", {target_room_id}, ...)` or `extend_sla`; `triage_flag` → `("approve"|"deny", {}, ...)`. Inject a fake `llm` seam returning the deterministic result; assert determinism (same inputs → identical output) and that rationale is non-empty templated text.
- [ ] **Step 2: Run red** → FAIL (module absent).
- [ ] **Step 3: Implement** pure `build(*, trigger, child, context, llm=_stub_llm) -> RecommendationDraft` (frozen dataclass `{action, params: dict, rationale_text}`). `llm` is an injectable seam; `_stub_llm` returns the templated rationale verbatim (LLM boxed — D5/D30). Action selection is the deterministic rule per spec §7.4.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/recommendation.py backend/tests/spine/test_recommendation.py
git commit -m "feat(domain): recommendation.build deterministic action + templated rationale (LLM seam stubbed)"
```

### Task C3: Per-entity lifecycle machines (`child`, `workorder`, `escalation`, `glitch`)

**Files:**
- Modify: `backend/conduit/shared/domain/lifecycle.py` → convert to package `lifecycle/` with `child.py`, `workorder.py`, `escalation.py`, `glitch.py`, `__init__.py`. (Preserve the existing `ChildState` enum + `_LEGAL` by moving them into `lifecycle/child.py`; keep `from conduit.shared.domain.lifecycle import ChildState` working via `__init__` re-export — verify no merged import breaks.)
- Test: `backend/tests/spine/test_lifecycle_machines.py` (create)

- [ ] **Step 1: Failing test** — each machine exposes `legal(frm, to) -> bool`; assert the full legal/illegal matrix for the dispatch arc (`triaged→routing→pushed→accepted→in_progress→done_pending_confirm→closed`; `done_pending_confirm→reopened`; any→`cancelled`), WorkOrder (`created→pushed|broadcast→accepted→in_progress→completed`), Escalation (`open→approved|edited|overridden|auto_proceeded|hard_escalated`), Glitch (`open→held_open|auto_closed|closed`). Illegal jumps return False.
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** each as a pure module with a `_LEGAL: dict[str,set[str]]` and `def legal(frm,to)`. No DB. Re-export `ChildState` from `lifecycle/__init__.py`.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/lifecycle/ backend/tests/spine/test_lifecycle_machines.py
git commit -m "feat(domain): per-entity lifecycle machines (child/workorder/escalation/glitch)"
```

### Task C4: The orchestrator `lifecycle.transition()` + writer extension

**Files:**
- Modify: `backend/conduit/shared/domain/lifecycle/__init__.py` (the orchestrator)
- Modify: `backend/conduit/shared/events/writer.py` (add `emit_*` for every new event type — one per type, mirroring `emit_child`/`emit_request_created`)
- Test: `backend/tests/spine/test_lifecycle_machines.py`

- [ ] **Step 1: Failing test** — `await transition(db, work_order, "completed", actor=..., )` on a valid `accepted→...→completed` path: asserts (a) `work_order.state=='completed'`, (b) exactly one `event` of type `work_order_completed` + its detail row, (c) the cross-entity hop fired: the child moved to `done_pending_confirm` and (if the issue code declares a downstream dept) a `CrossDeptNotification` row exists, (d) an illegal transition raises `ConflictError` and writes nothing.
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** `async def transition(s, subject, to, *, actor, **ctx)`: pick the machine by `type(subject)`, `if not machine.legal(subject.state, to): raise ConflictError`; set state; `await writer.emit_<event>(s, subject.id, actor)`; arm/cancel timers per the transition (e.g. child→routing arms accept_window+fulfilment_sla; accept cancels accept_window); perform cross-entity hops (WO completed→child done_pending_confirm[+CrossDeptNotification]; escalation relocate→call merged `supervisor.services.stays.relocate_stay` seam + close glitch). All in the caller's session; no commit. Extend `writer.py` with the new `emit_*` functions (one per new event type + detail).
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/lifecycle/__init__.py backend/conduit/shared/events/writer.py backend/tests/spine/test_lifecycle_machines.py
git commit -m "feat(domain): lifecycle.transition orchestrator + writer emit_* extension"
```

---

## Phase D — Spine (`shared/engine/spine.py`)

### Task D1: `spine.open_escalation` + Recommendation persistence + supervisor-SLA timer

**Files:**
- Modify: `backend/conduit/shared/engine/spine.py`
- Test: `backend/tests/spine/test_spine.py` (create)

- [ ] **Step 1: Failing test** — `open_escalation(db, child, trigger)` creates an `Escalation(open)`, a `Recommendation` + the right per-action detail row (from `recommendation.build`), one `escalation_opened` + one `recommendation_created` event, and arms a `supervisor_sla` `Timer` (fire_at = now + active `SLAPreset.supervisor_sla_seconds`).
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** per spec §7.4 using `recommendation.build` + `lifecycle.transition` + `timers.arm`. Resolve durations from the child's issue-code `SLAPreset` and the active `EscalationLadder`.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit** `feat(spine): open_escalation + recommendation + supervisor-SLA timer`.

### Task D2: `spine.apply_recommendation` (the single executor) + `hard_escalate` (D21 bound)

**Files:**
- Modify: `backend/conduit/shared/engine/spine.py`
- Test: `backend/tests/spine/test_spine.py`

- [ ] **Step 1: Failing test** — (a) `apply_recommendation(db, esc, outcome="approved")` executes the typed action (reassign→new WorkOrder assignee via `routing.select`, owner unchanged; relocate→merged `relocate_stay` + glitch closed; extend_sla→timer re-armed) and sets `escalation.state` accordingly + `resolved_by_account_id`; (b) `outcome="auto_proceeded"` produces the **identical** post-state except `resolved_by_account_id is None`; (c) when `cycle_count+1 >= active EscalationLadder.n_cycle_bound`, it `hard_escalate`s instead (state=`hard_escalated`, no auto-proceed).
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** the one executor exactly per §7.4. `hard_escalate` sets state + emits `escalation_resolved`(hard) and surfaces to duty manager (in-portal — no out-of-band).
- [ ] **Step 4: Run green** — PASS (esp. the silence≡approve state-equality assertion).
- [ ] **Step 5: Commit** `feat(spine): apply_recommendation single executor + D21 bounded hard_escalate`.

### Task D3: Wire `runner._fire_one` → spine; stall path

**Files:**
- Modify: `backend/conduit/shared/engine/runner.py`
- Test: `backend/tests/spine/test_engine.py`

- [ ] **Step 1: Failing test** — arm an `accept_window` timer `fire_at` in the past on a routed child with no accept; `await runner.tick(db)` → an `Escalation(stall)` opened with a deterministic `reassign`/`broadcast` recommendation + a `child` `revised_eta` set (D22). Then arm the `supervisor_sla` timer in the past, tick → auto-proceed reassign; repeat to N → `hard_escalated`.
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** `_fire_one` branching (spec §7.3) calling `spine.open_escalation` / `spine.apply_recommendation(outcome="auto_proceeded")` / `spine.hard_escalate`; set `child.revised_eta` on stall.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit** `feat(engine): runner stall→spine→auto-proceed→backstop wiring`.

### Task D4: Phase D checkpoint

- [ ] Run `cd backend && .venv/bin/pytest tests/spine -q`. Expected: all Phase A–D spine tests green. Record "Phase D complete — spine green end to end (engine-driven)."

---

## Phase E — Portal surfaces (guest, servicer, supervisor)

> Each portal: self-scoped DAL (no cross-portal DAL import — Resolution E) → guard service (delegates to `lifecycle.transition`/`spine`) → `extra="forbid"` schema → per-handler `require_roles` API → register in `<portal>/api/__init__.py`. Dedicated **action endpoints** for guarded transitions. No `DELETE` (assert 405). Each task is TDD: API test (full ASGI, real cookie chain) first.

### Task E1: Guest — status read + confirm/reopen/cancel

**Files:**
- Create: `backend/conduit/guest/dal/requests.py`, `services/conversation.py`, `schemas/requests.py`, `api/requests.py`
- Modify: `backend/conduit/guest/services/intake.py` (triage AUTO + mode=dispatch → routing-effect), `backend/conduit/guest/api/__init__.py`
- Test: `backend/tests/spine/test_guest_dispatch.py`

- [ ] **Step 1: Failing API test** — a guest with an active stay submits a dispatch-classifiable request via the merged intake endpoint → `GET /api/guest/requests` shows one card `state` progressing; `POST /api/guest/requests/{id}/confirm` on a `done_pending_confirm` child → `200`, child `closed`; `reopen` → `reopened`; `cancel` before closed → `200` + committed servicer notified (event asserted); foreign child → `404`; cancel after closed → `409`; `DELETE` any → `405`.
- [ ] **Step 2: Run red** → FAIL (routes absent).
- [ ] **Step 3: Implement** the DAL (self-scoped join: child + work_order.assigned servicer display name + revised_eta + glitch badge, filtered to the caller's active stay), service guards (`ownership`/`state` → `NotFoundError`/`ConflictError`, then `lifecycle.transition`), `extra="forbid"` schema, handlers committing at the edge. Extend `intake.py`: after triage, if `outcome=='auto'` and `fulfilment_mode=='dispatch'`, call the routing-effect entrypoint (`lifecycle.transition(child→'routing', ...)` which creates the WorkOrder + arms timers). Register the router.
- [ ] **Step 4: Run green** — PASS (all statuses).
- [ ] **Step 5: Commit** `feat(guest): dispatch status cards + confirm/reopen/cancel; intake→routing`.

### Task E2: Servicer — task queue + claim/accept/start/complete/raise

**Files:**
- Create: `backend/conduit/servicer/dal/tasks.py`, `services/tasks.py`, `schemas/tasks.py`, `api/tasks.py`
- Modify: `backend/conduit/servicer/api/__init__.py`
- Test: `backend/tests/spine/test_servicer_tasks.py`

- [ ] **Step 1: Failing API test** — rostered+working servicer (build via merged staffing services): `GET /api/servicer/tasks` shows pushed + claimable; `claim` a broadcast WO (`accountable_owner_id` unchanged — asserted); `accept`→`start`→`complete{notes}` walk; illegal order → `409`; not-in-zone claim → `403/409`; `raise{reason}` → `201` opens a `servicer_raised` escalation; `DELETE`→`405`; another servicer cannot see/act this servicer's pushed task (cross-account isolation).
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** self-scoped DAL (own pushed via `accountable_owner_id`/`assigned_servicer_id`; claimable via section broadcast + `effective_available`), service guards delegating to `lifecycle.transition`/`spine.open_escalation(servicer_raised)`, schema, handlers. Register router.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit** `feat(servicer): task queue + accept/complete/claim/raise`.

### Task E3: Supervisor — decision queue + resolve (one executor)

**Files:**
- Create: `backend/conduit/supervisor/dal/decisions.py`, `services/decisions.py`, `schemas/decisions.py`, `api/decisions.py`
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_supervisor_decisions.py`

- [ ] **Step 1: Failing API test** — `GET /api/supervisor/decisions` lists open escalations w/ recommendation + per-action detail + supervisor-SLA deadline + cycle; `POST /decisions/{id}/resolve {action:"approve"}` → executes via `spine.apply_recommendation` (`resolved_by_account_id` set); `{action:"edit", payload:{...}}` overrides the action; resolving an already-resolved → `409`; bad payload → `422`; guest/servicer → `403`; no cookie → `401`; `DELETE`→`405`. Assert the resolved-by-human end state equals the auto-proceeded end state (besides `resolved_by_account_id`) — the symmetry guard.
- [ ] **Step 2: Run red** → FAIL.
- [ ] **Step 3: Implement** DAL read (join escalation+recommendation+detail+timer deadline), service `resolve(...)` → `spine.apply_recommendation(outcome=...)`, schema, handler. Register router.
- [ ] **Step 4: Run green** — PASS.
- [ ] **Step 5: Commit** `feat(supervisor): decision queue + /resolve (shared executor; silence≡approve)`.

### Task E4: Supervisor — Task Explorer/Override (D6)

**Files:**
- Create: `backend/conduit/supervisor/dal/children.py`, `services/override.py`, `api/override.py` (+ schema in `schemas/decisions.py` or a new `schemas/override.py`)
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_supervisor_decisions.py`

- [ ] **Step 1: Failing test** — `GET /api/supervisor/children?...` finds any child + its WO/escalation/glitch; `POST /children/{id}/takeover|reassign|cancel` works from any state (D6); `DELETE`→`405`; role gates.
- [ ] **Step 2: Run red** → FAIL. **Step 3: Implement** via `lifecycle.transition` god-mode (interruptible from every state — guarded transitions, not a special node). **Step 4: green. Step 5: Commit** `feat(supervisor): task explorer + override (D6)`.

### Task E5: Supervisor — SLA presets + escalation ladder CRUD (issue_code idiom)

**Files:**
- Create: `backend/conduit/supervisor/dal/sla_presets.py`, `escalation_ladder.py`, `services/setup.py`, `schemas/setup.py`, `api/setup.py`
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_supervisor_setup.py`

- [ ] **Step 1: Failing test** — `GET/POST/PATCH /api/supervisor/sla-presets` and `/escalation-ladder`: create (201), duplicate active tier/ladder → `409` (service + partial-unique backstop), incoherent durations (≤0) → `422`, disable via PATCH `status` (no `DELETE`; `DELETE`→`405`), role gates. One append-only event per mutation.
- [ ] **Step 2: Run red** → FAIL. **Step 3: Implement** the `issue_code.py` CRUD idiom verbatim (DAL add-only, service guard+flush+emit, handler commit). **Step 4: green. Step 5: Commit** `feat(supervisor): SLAPreset + EscalationLadder CRUD (disable-not-delete)`.

### Task E6: Supervisor — awareness stream (first event read model)

**Files:**
- Create: `backend/conduit/supervisor/dal/awareness.py`, `schemas/awareness.py`, `api/decisions.py` route addition (or `api/awareness.py`)
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_awareness.py`

- [ ] **Step 1: Failing test** — drive a happy-path + a glitch through the spine, then `GET /api/supervisor/awareness` returns one composite projection: incoming · task delegation · servicer recent work · open glitches, computed **from the `event`+detail log** (not the core tables directly). Glitch appears while open and disappears once auto-closed. Role gates; `DELETE`→`405`.
- [ ] **Step 2: Run red** → FAIL. **Step 3: Implement** the read-only projection query over `event` joined to detail; no writes, no commit. **Step 4: green. Step 5: Commit** `feat(supervisor): awareness stream — first event read model (polled)`.

### Task E7: Phase E checkpoint + contract snapshot regeneration

- [ ] **Step 1:** `cd backend && .venv/bin/pytest -q`. The inherited route/contract snapshot guard is now **legitimately red** (new routes). Regenerate as the conscious step: delete `backend/tests/api/contract_snapshot.json` (path per merged guard), re-run the suite (the guard recreates then enforces), eyeball the diff to confirm only the intended new routes/shapes appear.
- [ ] **Step 2: Commit** `test: regenerate route/contract snapshot for dispatch+spine routes (intentional)`.

---

## Phase F — Frontend

> Reuse the merged uniformity layer verbatim (TanStack Query array keys, `api` client, `data-table-shell`/`confirm`/`combobox-field`/`page-header`, monochrome tokens). shadcn add-then-edit only; do not re-`add` an edited component. Each task ends with `npm run build` green + commit.

### Task F1: `countdown.tsx` shared primitive

**Files:** Create `frontend/src/components/common/countdown.tsx`. Test: `npm run build` (typecheck) — plus a lightweight render assertion if a test runner exists in the merged FE; otherwise build-only.
- [ ] Implement a client-ticking countdown taking an ISO `deadline` prop, re-synced on prop change, never deriving "now" from anything but the prop+local tick. Build green. Commit `feat(ui): countdown primitive (server-deadline driven)`.

### Task F2: Guest status card + conversation hook

**Files:** Modify `frontend/src/components/common/child-status-card.tsx`, `frontend/src/shell/guest/hooks/use-conversation.ts`, `frontend/src/shell/guest/pages/conversation.tsx`.
- [ ] Extend the card to the dispatch lifecycle states + named servicer (D17) + `revised_eta` (via `countdown`) + glitch badge; swap closure-lite→confirm/reopen for dispatch children; add `confirm`/`reopen`/`cancel` mutations to `use-conversation` (array keys, invalidate `['guest','requests']`, polled per AD7). Build green. Commit `feat(guest-ui): dispatch status cards + confirm/reopen/cancel`.

### Task F3: Servicer queue-as-index + task detail

**Files:** Modify `frontend/src/shell/servicer/index.tsx`; create `frontend/src/shell/servicer/hooks/use-tasks.ts`, `frontend/src/shell/servicer/pages/task-detail.tsx`; modify `frontend/src/App.tsx`.
- [ ] Make index the Task Queue with staffing's `shift-card`+`presence-control` composed as a compact sticky header; task detail Sheet (accept/start/complete-notes/raise). `use-tasks` polled. Route wired. Build green. Commit `feat(servicer-ui): queue-as-index + task detail`.

### Task F4: Supervisor decision queue + awareness + explorer + setup pages

**Files:** Create `frontend/src/shell/supervisor/pages/{decisions,awareness,task-explorer,sla-presets,escalation-ladder}.tsx` + `hooks/{use-decisions,use-awareness,use-children,use-sla-presets,use-escalation-ladder}.ts`; modify `frontend/src/shell/supervisor/nav.tsx`, `frontend/src/App.tsx`.
- [ ] Decisions page: recommendation + per-action editable form mirroring the rec detail tables + auto-proceed `countdown`; resolve mutation. Awareness page: the composite projection (separate route — D2), polled. Explorer: search + takeover/reassign/cancel. SLA presets + ladder pages on the `issue-code-form-dialog` CONFIG pattern (disable-not-delete via `confirm`). Nav + routes wired. Build green. Commit `feat(supervisor-ui): decisions + awareness + explorer + sla/ladder setup`.

---

## Phase G — Structural guards + E2E sentinel

### Task G1: Structural guards (asserted, not inherited-only)

**Files:** Create `backend/tests/spine/test_structural_guards.py`.
- [ ] Assert, as explicit tests over the new surface: (1) every new `/api` route present in the auth-coverage sweep (401/403 without cookie); (2) response parse-back through each `extra="forbid"` schema (no internal field leak); (3) role×endpoint matrix (guest/servicer/supervisor/duty_manager/unauth → exact allow/deny) for every new route; (4) append-only: every mutation emits exactly one `event`+detail and no event has an update/delete path; (5) no-`DELETE`→`405` over every new route; (6) the timer one-subject CHECK, work_order/glitch unique child, partial-unique indexes (re-assert at the suite level). Run red→implement→green. Commit `test(spine): structural guards over the dispatch+spine surface`.

### Task G2: E2E dispatch sentinel

**Files:** Create `backend/tests/spine/test_e2e_dispatch.py`.
- [ ] One scripted async test = the journey, time pinned via `fire_at`+explicit `runner.tick`: seed property/SLA presets/ladder → guest dispatch request → triage AUTO → route to D12 owner → **(a)** accept→complete→guest confirm→CLOSED; **(b)** stall: no accept, `fire_at`-past + tick → stall + revised_eta → silence, supervisor-SLA tick → auto-proceed reassign → repeat to N → duty-manager hard-escalate; **(c)** glitch: problem_report P1 → Glitch open → servicer raise → relocate recommendation → resolve → merged `relocate_stay` re-bind → Glitch+WO closed → `CrossDeptNotification` emitted. Assert exactly one append-only event per transition, the silence≡approve state equality, and zero residue on a forced failure (savepoint rollback). Run red→implement→green. Commit `test(spine): e2e dispatch journey sentinel`.

### Task G3: Phase G checkpoint — full suite + coverage gate

- [ ] Run `cd backend && .venv/bin/pytest -q` (full suite incl. `--cov-fail-under=90`, savepoint isolation, leak sentinel) and `cd frontend && npm run build`. Both green. The coverage gate scope is **unchanged** per spec §11 (do not edit `pyproject.toml` cov flags — the new packages are covered by explicit tests; raising/rescoping the gate moves the bar for merged code). If red, fix forward; do not weaken the gate. Commit nothing (verification). Record "Phase G complete — full bench green."

---

## Phase H — Land: commit, push, PR

### Task H1: Final verification sweep

- [ ] Run, from the worktree:
```bash
cd /workspace/Conduit-dispatch-spine/backend
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
.venv/bin/pytest -q
cd ../frontend && npm run build
cd .. && git status --porcelain
```
Expected: migration round-trips; full suite green; FE build green; **no untracked `.env`** (git status clean except intended files; `backend/.env`/`frontend/.env` must NOT appear — they are gitignored). If `.env` appears, STOP and fix `.gitignore` handling before pushing.

### Task H2: Push the branch

- [ ] Run:
```bash
cd /workspace/Conduit-dispatch-spine
git log --oneline origin/main..HEAD | wc -l   # sanity: the phased commits
git push -u origin feat/dispatch-spine
```
Expected: branch pushed; no `.env` in the diff.

### Task H3: Raise the PR

- [ ] Run (PR body cites only D-/AD-series + Conduit docs — no external reference):
```bash
gh pr create --base main --head feat/dispatch-spine \
  --title "Dispatch & Escalation Spine slice" \
  --body "$(cat <<'EOF'
Implements the dispatch journey + escalation spine + Glitch + cross-dept
notification + supervisor decision-queue/awareness + SLA/ladder config,
single-intent, stacked on 0004_staffing (migration 0005_dispatch_spine).

Design: docs/superpowers/specs/2026-05-16-dispatch-spine-design.md
Plan:   docs/superpowers/plans/2026-05-16-dispatch-spine.md

Built in verified phases (A data model → B engine → C domain → D spine →
E portals → F frontend → G guards/e2e). Shared-owned spine; pure
routing.select; AD5 durable timers (fire_at+tick test seam); one
apply_recommendation executor (silence ≡ approve, structural). No DELETE
(405 asserted); disable-not-delete; append-only event log + the first
read model (awareness/decision projections). Deferred seams named in the
spec §13 (D35 fan-out, D24+reservation_facts, D38 modify, analytics).

Verification: migration round-trips; full savepoint-isolated bench green
incl. coverage gate + structural guards + e2e sentinel; FE build green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR created against `main`. Report the PR URL.

---

## Self-review (run before execution)

**1. Spec coverage:** §6 data model → Phase A (A1–A7). §7.3 timers → Phase B. §7.1 routing / §7.2 lifecycle / §7.4 recommendation → Phase C. §7.4 spine/auto-proceed/D21 → Phase D. §8 API + §9 journeys → Phase E. §10 frontend → Phase F. §11 bench (savepoint, fire_at+tick, structural guards, e2e, contract snapshot) → Phases A8/E7/G. §12 verification bar → H1. §13 deferred seams → asserted absent (single-intent, no `decompose`, `predecessor_child_id` inert, no `reservation_facts`, no modify route, no analytics route). Worktree/env/.env-copy/venv/push/PR + Opus-subagent + no-external-reference constraints → Operating constraints + Task 0 + H1–H3. No gap found.

**2. Placeholder scan:** Test bodies in C1/E* are specified by exact cases and asserted fields; the executing worker writes them per the named cases (no "TODO"/"similar to"/"add error handling" — every guard/status to assert is enumerated). Load-bearing code (models, timers, runner.tick, routing signature, orchestrator, spine) is given concretely. No "TBD".

**3. Type/name consistency:** `Selection`, `RecommendationDraft`, `timers.arm(subject_kind,...)`, `runner.tick`, `spine.open_escalation/apply_recommendation/hard_escalate`, `lifecycle.transition`, model/table names, and event-type strings are used identically across tasks and match spec §5/§6/§7.

If execution surfaces a mismatch with the merged staffing code (e.g. a renamed fixture/helper), fix forward in-task and keep the phase checkpoint green before proceeding.
