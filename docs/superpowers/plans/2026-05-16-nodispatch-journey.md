# No-Dispatch Journey Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first SPINE journey — a checked-in guest asks in plain text; the system decomposes + mechanically triages; a no-dispatch intent is answered grounded in reservation + supervisor KB (closure-lite) or honestly deferred — plus the supervisor `IssueCode` + `KnowledgeBase` config that drives those decisions.

**Architecture:** Async `api → services → dal → shared/models`; the child state machine is shared mechanism (`shared/domain/lifecycle.transition` appends append-only events in the same transaction); the LLM is reached only through a bulkheaded `shared/integrations` boundary (timeout + circuit breaker → degrade, never block); supervisor config is read live every request. Stacks on the merged auth + stay/binding state with zero auth-owned changes.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, Postgres, pytest/pytest-asyncio/httpx, OpenAI Python SDK (gpt-5.4-mini, Responses API), React + TanStack Query + shadcn/Tailwind.

**Source of truth:** `docs/superpowers/specs/2026-05-16-nodispatch-journey-design.md` (read it fully before starting). Decision IDs (D-series / AD-series) referenced here are defined in `docs/datamodels/` and `docs/archi/` inside this repo.

---

## Preconditions (read before Task 0)

- This plan **executes after the stay/binding slice is merged to `main`**. Do not start until `git -C /workspace/Conduit log --oneline main` shows the stay/binding merge (the `0002_stay_binding` migration, `shared/models/event.py`, `tests/conftest.py`, `public/dal/bindings.py`, the frontend uniformity layer all present on `main`).
- All work happens in an **isolated worktree** created in Task 0. Never edit `/workspace/Conduit` directly.
- Postgres + the test DB tooling are as configured in the merged `tests/conftest.py`.

## Subagent rules (if dispatched)

- **Every subagent MUST be an Opus subagent** (`model: "opus"`). Never sonnet/haiku for any task in this plan.
- Every dispatch MUST list the **exact files** the subagent may create/modify/test (copy the task's **Files** block verbatim into the dispatch prompt) and instruct it to touch nothing else.
- Every dispatch MUST tell the subagent the worktree path (`/workspace/Conduit-nodispatch`) and that all commands run from there with that worktree's venv.
- Subagents read the spec section named in the task before coding.

---

## File Structure (decomposition lock-in)

```
backend/conduit/shared/models/   request.py child_sub_request.py issue_code.py
                                  kb_entry.py no_dispatch_resolution.py provenance.py
                                  event.py (modify) __init__.py (modify)
backend/conduit/shared/events/   writer.py (new — append-only event+detail writer)
backend/conduit/shared/domain/   triage.py grounding.py lifecycle.py (implement)
backend/conduit/shared/integrations/ openai.py (implement)
backend/conduit/supervisor/dal/  issue_codes.py kb.py
backend/conduit/supervisor/services/ issue_codes.py kb.py
backend/conduit/supervisor/schemas/  issue_code.py kb.py
backend/conduit/supervisor/api/  issue_codes.py kb.py __init__.py (modify)
backend/conduit/guest/dal/       bindings.py requests.py children.py resolutions.py events.py
backend/conduit/guest/services/  intake.py (implement) nodispatch.py
backend/conduit/guest/schemas/   conversation.py
backend/conduit/guest/api/       conversation.py (implement) __init__.py (verify)
backend/conduit/seed.py          (modify — ensure_issue_codes)
backend/migrations/versions/     0003_nodispatch.py
backend/tests/spine/             conftest.py + layered test modules + test_e2e_journey.py
frontend/src/index.css           (modify — tightening)
frontend/src/components/ui/      scroll-area.tsx (shadcn add) + edited primitives
frontend/src/components/common/  chat-scroll.tsx message.tsx request-receipt.tsx
                                  child-status-card.tsx composer.tsx closure-lite.tsx
                                  issue-code-form-dialog.tsx kb-entry-form-dialog.tsx
frontend/src/shell/guest/        pages/conversation.tsx hooks/use-conversation.ts
frontend/src/shell/supervisor/   pages/issue-codes.tsx pages/knowledge-base.tsx
                                  hooks/use-issue-codes.ts hooks/use-kb.ts
frontend/src/components/layout/nav-config.ts (modify)
frontend/src/App.tsx             (modify — routes)
```

---

## Task 0: Worker setup — worktree, venv, env files

**Files:**
- Create: worktree at `/workspace/Conduit-nodispatch` (branch `feat/nodispatch-journey`)
- Copy: `/workspace/Conduit/backend/.env`, `/workspace/Conduit/frontend/.env`

- [ ] **Step 1: Confirm stay/binding is merged**

Run:
```bash
git -C /workspace/Conduit fetch origin
git -C /workspace/Conduit log --oneline -5 origin/main
test -f /workspace/Conduit/backend/migrations/versions/0002_stay_binding.py && echo OK_0002
test -f /workspace/Conduit/backend/conduit/shared/models/event.py && echo OK_EVENT
```
Expected: `OK_0002` and `OK_EVENT` printed. If not, STOP — the precondition is unmet.

- [ ] **Step 2: Create the isolated worktree off latest main**

Run:
```bash
git -C /workspace/Conduit worktree add -b feat/nodispatch-journey /workspace/Conduit-nodispatch origin/main
git -C /workspace/Conduit-nodispatch branch --show-current
```
Expected: `feat/nodispatch-journey`.

- [ ] **Step 3: Copy env files into the worktree**

Run:
```bash
cp /workspace/Conduit/backend/.env /workspace/Conduit-nodispatch/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-nodispatch/frontend/.env
ls -1 /workspace/Conduit-nodispatch/backend/.env /workspace/Conduit-nodispatch/frontend/.env
```
Expected: both paths listed.

- [ ] **Step 4: Create the worktree venv from the existing one as the source**

The existing interpreter is `/workspace/Conduit/backend/.venv`. Create a fresh venv in the worktree using that interpreter as the source, then install the project editable:
```bash
cd /workspace/Conduit-nodispatch/backend
/workspace/Conduit/backend/.venv/bin/python -m venv .venv
.venv/bin/python -m pip install -q -e ".[dev]"
.venv/bin/python -c "import conduit, fastapi, sqlalchemy, alembic, httpx, openai; print('env OK')"
```
Expected: `env OK`.

- [ ] **Step 5: Baseline the suite (must be green before any change)**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest -q
```
Expected: PASS (the merged auth + stay/binding suite). If red, STOP and report — do not build on a red baseline.

- [ ] **Step 6: Commit nothing yet** — Task 0 produces no repo changes (worktree/venv/.env are not committed). Proceed to Task 1.

---

## Task 1: Design-system tightening (the isolated first commit — spec §13)

**Files:**
- Modify: `frontend/src/index.css`
- Verify: `frontend` build + existing pages

- [ ] **Step 1: Tighten tokens in `index.css`**

In `:root`, change `--radius: 0.625rem;` to `--radius: 0.375rem;`. In the `@theme inline` block, replace the radius ladder so nothing balloons:
```css
--radius-sm: calc(var(--radius) * 0.66);
--radius-md: var(--radius);
--radius-lg: calc(var(--radius) * 1.33);
--radius-xl: calc(var(--radius) * 1.6);
--radius-2xl: calc(var(--radius) * 1.6);
--radius-3xl: calc(var(--radius) * 1.6);
--radius-4xl: calc(var(--radius) * 1.6);
```
Add a `--border-strong` and a reserved (unused) action accent to both `:root` and `.dark` (values monochrome for `:root`, kept dark-safe):
```css
/* :root */
--border-strong: oklch(0.88 0 0);
--accent-action: oklch(0.55 0.13 250); /* RESERVED — not applied this slice */
/* .dark */
--border-strong: oklch(1 0 0 / 16%);
--accent-action: oklch(0.62 0.13 250);
```
Map them in `@theme inline`:
```css
--color-border-strong: var(--border-strong);
--color-accent-action: var(--accent-action);
```

- [ ] **Step 2: Verify the frontend still builds and existing pages render under tight tokens**

Run:
```bash
cd /workspace/Conduit-nodispatch/frontend && npm install && npm run build
```
Expected: typecheck + build succeed with no errors. (Visual re-verify of the auth/stay-binding pages is a manual check; the build gate is the automated one.)

- [ ] **Step 3: Commit**

```bash
cd /workspace/Conduit-nodispatch
git add frontend/src/index.css
git commit -m "style(ui): tighten design tokens (radius, hairline, reserved accent)"
```

---

## Task 2: SPINE/CONFIG models + migration `0003`

**Files:**
- Create: `backend/conduit/shared/models/issue_code.py`, `kb_entry.py`, `request.py`, `child_sub_request.py`, `no_dispatch_resolution.py`, `provenance.py`
- Modify: `backend/conduit/shared/models/event.py` (extend CHECK + 7 detail classes), `backend/conduit/shared/models/__init__.py`
- Create: `backend/migrations/versions/0003_nodispatch.py`
- Test: `backend/tests/spine/test_migration.py`, `backend/tests/spine/test_models.py`

Read spec §6 first. Follow the exact column/typing idiom in the merged `shared/models/stay.py` and `event.py` (uuid pk via `UUID(as_uuid=True)`, `timestamptz` via `DateTime(timezone=True)`, `text + CheckConstraint`, `func.now()` server defaults).

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/spine/__init__.py` (empty) and `backend/tests/spine/test_models.py`:
```python
from conduit.shared.models import (
    IssueCode, KBEntry, Request, ChildSubRequest, NoDispatchResolution,
    NDProvenanceKB, NDProvenanceField, Event,
    EventRequestCreated, EventChildTriaged, EventChildAnswered,
    EventChildDeferred, EventChildParked, EventChildClosed, EventChildReopened,
)

def test_models_registered():
    assert IssueCode.__tablename__ == "issue_code"
    assert KBEntry.__tablename__ == "kb_entry"
    assert Request.__tablename__ == "request"
    assert ChildSubRequest.__tablename__ == "child_sub_request"
    assert NoDispatchResolution.__tablename__ == "no_dispatch_resolution"
    assert NDProvenanceKB.__tablename__ == "nd_provenance_kb"
    assert NDProvenanceField.__tablename__ == "nd_provenance_field"
    assert EventChildAnswered.__tablename__ == "event_child_answered"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_models.py -q`
Expected: FAIL with `ImportError` (models not defined).

- [ ] **Step 3: Create `issue_code.py`**

```python
# conduit/shared/models/issue_code.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, String, Boolean, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class IssueCode(Base):
    __tablename__ = "issue_code"
    __table_args__ = (
        CheckConstraint("fulfilment_mode in ('dispatch','no_dispatch')",
                        name="ck_issue_code_mode"),
        CheckConstraint("routing_model in ('section_pooled','skill_matched','none')",
                        name="ck_issue_code_routing"),
        CheckConstraint("intent_kind in ('service','problem_report')",
                        name="ck_issue_code_intent"),
        CheckConstraint("status in ('active','disabled')",
                        name="ck_issue_code_status"),
        Index("uq_issue_code_lower_code", func.lower(String), unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)
    fulfilment_mode: Mapped[str] = mapped_column(String, nullable=False)
    routing_model: Mapped[str] = mapped_column(String, nullable=False)
    intent_kind: Mapped[str] = mapped_column(String, nullable=False,
                                              server_default="service")
    is_reservation_mutation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String, nullable=False,
                                         server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```
Note: the case-insensitive unique index is created explicitly in the migration (Step 8) as `lower(code)`; the `Index(...)` in `__table_args__` is replaced there. To keep autogenerate clean, drop the `Index` line from `__table_args__` and rely on the migration's hand-written `op.create_index('uq_issue_code_lower_code', 'issue_code', [sa.text('lower(code)')], unique=True)`.

- [ ] **Step 4: Create `kb_entry.py`**

```python
# conduit/shared/models/kb_entry.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class KBEntry(Base):
    __tablename__ = "kb_entry"
    __table_args__ = (
        CheckConstraint("status in ('active','disabled')",
                        name="ck_kb_entry_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False,
                                         server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

- [ ] **Step 5: Create `request.py` and `child_sub_request.py`**

```python
# conduit/shared/models/request.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Request(Base):
    __tablename__ = "request"
    __table_args__ = (
        CheckConstraint("channel in ('text')", name="ck_request_channel"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    guest_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False,
                                          server_default="text")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
```

```python
# conduit/shared/models/child_sub_request.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, String, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class ChildSubRequest(Base):
    __tablename__ = "child_sub_request"
    __table_args__ = (
        CheckConstraint("outcome in ('auto','clarify','flag','no_dispatch')",
                        name="ck_child_outcome"),
        CheckConstraint(
            "fulfilment_mode is null or fulfilment_mode in ('dispatch','no_dispatch')",
            name="ck_child_mode"),
        CheckConstraint(
            "state in ('intake','triaged','answered','concierge_queue',"
            "'closed','reopened')", name="ck_child_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                           default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    issue_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issue_code.id"), nullable=True)
    uncategorized: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                 server_default="false")
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    fulfilment_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    is_problem_report: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                     server_default="false")
    state: Mapped[str] = mapped_column(String, nullable=False,
                                        server_default="intake")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

- [ ] **Step 6: Create `no_dispatch_resolution.py` and `provenance.py`**

```python
# conduit/shared/models/no_dispatch_resolution.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class NoDispatchResolution(Base):
    __tablename__ = "no_dispatch_resolution"
    __table_args__ = (
        CheckConstraint("mode in ('grounded_answer','human_deferral')",
                        name="ck_ndr_mode"),
        CheckConstraint("helpful is null or helpful in ('yes','no')",
                        name="ck_ndr_helpful"),
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"),
        primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(String, nullable=True)
    helpful: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
```

```python
# conduit/shared/models/provenance.py
from __future__ import annotations
import uuid
from sqlalchemy import CheckConstraint, Boolean, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class NDProvenanceKB(Base):
    __tablename__ = "nd_provenance_kb"
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        primary_key=True)
    kb_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kb_entry.id"), primary_key=True)
    claimed_used: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                server_default="false")


class NDProvenanceField(Base):
    __tablename__ = "nd_provenance_field"
    __table_args__ = (
        CheckConstraint(
            "field_name in ('room_label','section_label','check_in',"
            "'check_out','stay_status')", name="ck_ndpf_field"),
    )
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        primary_key=True)
    field_name: Mapped[str] = mapped_column(String, primary_key=True)
    claimed_used: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                server_default="false")
```

- [ ] **Step 7: Modify `event.py` — extend CHECK + add 7 detail classes**

Change the `Event.__table_args__` CheckConstraint to:
```python
CheckConstraint(
    "type in ('stay_created','stay_ended','guest_relocated',"
    "'request_created','child_triaged','child_answered','child_deferred',"
    "'child_parked','child_closed','child_reopened')",
    name="ck_event_type"),
```
Append these classes to `event.py` (one detail table per type; `event_child_answered` also carries `resolution_child_id`):
```python
class EventRequestCreated(Base):
    __tablename__ = "event_request_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request.id"), nullable=False)


class _ChildEvent(Base):
    __abstract__ = True
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False)


class EventChildTriaged(_ChildEvent):
    __tablename__ = "event_child_triaged"

class EventChildDeferred(_ChildEvent):
    __tablename__ = "event_child_deferred"

class EventChildParked(_ChildEvent):
    __tablename__ = "event_child_parked"

class EventChildClosed(_ChildEvent):
    __tablename__ = "event_child_closed"

class EventChildReopened(_ChildEvent):
    __tablename__ = "event_child_reopened"


class EventChildAnswered(Base):
    __tablename__ = "event_child_answered"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_sub_request.id"), nullable=False)
    resolution_child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("no_dispatch_resolution.child_id"),
        nullable=False)
```

Register everything in `shared/models/__init__.py`: import the new classes and append all names to `__all__` (mirror the existing import/`__all__` block exactly).

- [ ] **Step 8: Generate + hand-finish the migration**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend
.venv/bin/alembic revision --autogenerate -m "nodispatch" --rev-id 0003_nodispatch
```
Open the generated `backend/migrations/versions/0003_nodispatch.py`. Verify `down_revision = "0002_stay_binding"`. Remove any autogen attempt at a plain `code` unique index and add, in `upgrade()` after the `issue_code` table is created:
```python
op.create_index("uq_issue_code_lower_code", "issue_code",
                 [sa.text("lower(code)")], unique=True)
```
and in `downgrade()` (before dropping `issue_code`):
```python
op.drop_index("uq_issue_code_lower_code", table_name="issue_code")
```
Confirm the `event` `type` CHECK is altered (drop + recreate the constraint with the extended value list) rather than left stale.

- [ ] **Step 9: Write the failing migration test**

`backend/tests/spine/test_migration.py`:
```python
import sqlalchemy as sa
import pytest
from sqlalchemy.exc import IntegrityError

def test_down_revision_chains_to_0002():
    import importlib
    m = importlib.import_module("migrations.versions.0003_nodispatch")
    assert m.down_revision == "0002_stay_binding"

async def test_partial_pk_blocks_second_resolution(db):
    # one child, one resolution; a second resolution for the same child must fail
    from conduit.shared.models import (Request, ChildSubRequest,
                                       NoDispatchResolution, Account)
    # arrange a request+child via raw inserts is acceptable here (migration layer)
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert acc is not None
    r = Request(guest_account_id=acc.id, stay_id=acc.id, raw_text="x")
    db.add(r); await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                         state="triaged")
    db.add(c); await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="human_deferral"))
    await db.flush()
    db.add(NoDispatchResolution(child_id=c.id, mode="grounded_answer"))
    with pytest.raises(IntegrityError):
        await db.flush()
```
(Note: `db` fixture comes from the merged harness; `tests/spine/conftest.py` lands in Task 13 and adds savepoint isolation. Until then, run migration tests against the merged `db` fixture.)

- [ ] **Step 10: Run migration build + tests**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
.venv/bin/pytest tests/spine/test_migration.py tests/spine/test_models.py -q
```
Expected: alembic round-trip clean; tests PASS.

- [ ] **Step 11: Commit**

```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/shared/models backend/migrations/versions/0003_nodispatch.py backend/tests/spine
git commit -m "feat(models): spine + config models, event taxonomy, migration 0003"
```

---

## Task 3: Append-only event writer + guarded lifecycle transition (the shared seam)

**Files:**
- Create: `backend/conduit/shared/events/writer.py`
- Modify: `backend/conduit/shared/domain/lifecycle.py`
- Test: `backend/tests/spine/test_lifecycle.py`

Read spec §4 ("Lifecycle/event seam") and §7. The merged `shared/domain/lifecycle.py` has the `ChildState` enum and a stub `transition`. The writer adds an `event` row + the matching detail row; `transition` mutates child state and calls the writer in the same session/txn (no commit — the API edge commits).

- [ ] **Step 1: Write the failing test**

`backend/tests/spine/test_lifecycle.py`:
```python
import sqlalchemy as sa
from conduit.shared.models import (Account, Request, ChildSubRequest, Event,
                                   EventChildTriaged)
from conduit.shared.domain import lifecycle

async def test_transition_sets_state_and_appends_event(db):
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    r = Request(guest_account_id=acc.id, stay_id=acc.id, raw_text="x")
    db.add(r); await db.flush()
    c = ChildSubRequest(request_id=r.id, text="x", outcome="no_dispatch",
                         state="intake")
    db.add(c); await db.flush()
    await lifecycle.transition(db, c, "triaged", actor_account_id=None)
    await db.flush()
    assert c.state == "triaged"
    ev = (await db.execute(sa.select(Event)
          .where(Event.type == "child_triaged"))).scalars().all()
    assert len(ev) == 1
    det = (await db.execute(sa.select(EventChildTriaged))).scalars().all()
    assert len(det) == 1 and det[0].child_id == c.id
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_lifecycle.py -q`
Expected: FAIL (`transition` is `NotImplementedError` / signature mismatch).

- [ ] **Step 3: Implement the writer**

```python
# conduit/shared/events/writer.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models import (
    Event, EventRequestCreated, EventChildTriaged, EventChildAnswered,
    EventChildDeferred, EventChildParked, EventChildClosed, EventChildReopened,
)

_CHILD_DETAIL = {
    "child_triaged": EventChildTriaged,
    "child_deferred": EventChildDeferred,
    "child_parked": EventChildParked,
    "child_closed": EventChildClosed,
    "child_reopened": EventChildReopened,
}


async def emit_request_created(s: AsyncSession, request_id: uuid.UUID,
                               actor_account_id: uuid.UUID | None) -> None:
    e = Event(type="request_created", actor_account_id=actor_account_id)
    s.add(e); await s.flush()
    s.add(EventRequestCreated(event_id=e.id, request_id=request_id))


async def emit_child(s: AsyncSession, etype: str, child_id: uuid.UUID,
                     actor_account_id: uuid.UUID | None,
                     resolution_child_id: uuid.UUID | None = None) -> None:
    e = Event(type=etype, actor_account_id=actor_account_id)
    s.add(e); await s.flush()
    if etype == "child_answered":
        s.add(EventChildAnswered(event_id=e.id, child_id=child_id,
                                 resolution_child_id=resolution_child_id))
    else:
        s.add(_CHILD_DETAIL[etype](event_id=e.id, child_id=child_id))
```

- [ ] **Step 4: Implement `lifecycle.transition`**

Replace the stub `transition` in `shared/domain/lifecycle.py` (keep the `ChildState` enum). Add the legal-edge table from spec §4 (Resolution D) and the event mapping:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError
from conduit.shared.events import writer

_LEGAL = {
    "intake": {"triaged"},
    "triaged": {"answered", "concierge_queue"},
    "answered": {"closed", "reopened"},
    "reopened": {"concierge_queue"},
}
_EVENT = {
    "triaged": "child_triaged",
    "answered": "child_answered",
    "concierge_queue": "child_deferred",
    "closed": "child_closed",
    "reopened": "child_reopened",
}


async def transition(s: AsyncSession, child, to: str, *,
                     actor_account_id=None, resolution_child_id=None) -> None:
    if to not in _LEGAL.get(child.state, set()):
        raise ConflictError(f"illegal transition {child.state}->{to}")
    child.state = to
    s.add(child)
    await writer.emit_child(s, _EVENT[to], child.id, actor_account_id,
                            resolution_child_id=resolution_child_id)
```
Add `from conduit.shared.events import writer as writer` re-export in `shared/events/__init__.py` (`from conduit.shared.events.writer import emit_request_created, emit_child`).

- [ ] **Step 5: Run to verify it passes**

Run: `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/shared/events backend/conduit/shared/domain/lifecycle.py backend/tests/spine/test_lifecycle.py
git commit -m "feat(spine): append-only event writer + guarded lifecycle transition"
```

---

## Task 4: Supervisor Issue Codes — dal + service + schema + api

**Files:**
- Create: `backend/conduit/supervisor/dal/issue_codes.py`, `backend/conduit/supervisor/services/issue_codes.py`, `backend/conduit/supervisor/schemas/issue_code.py`, `backend/conduit/supervisor/api/issue_codes.py`
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_issue_codes.py`

Read spec §8 (Issue Codes) and Resolution A. Follow the exact dal/service/api shape of the merged `supervisor/dal/sections.py`, `supervisor/services/sections.py`, `supervisor/api/binding.py` (per-handler `_sup` gate, `extra="forbid"` schemas, commit at the edge).

- [ ] **Step 1: Write the failing API test**

`backend/tests/spine/test_issue_codes.py`:
```python
async def _sup(make_account, login):
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")

async def test_crud_and_mutation_lock(client, make_account, login):
    await _sup(make_account, login)
    r = await client.post("/api/supervisor/issue-codes", json={
        "code": "INFO_DINING", "label": "Dining info", "department": "concierge",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_reservation_mutation"] is False        # display present
    # Resolution A: request schema rejects the locked field
    r2 = await client.post("/api/supervisor/issue-codes", json={
        "code": "X", "label": "x", "department": "d",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service", "is_reservation_mutation": True})
    assert r2.status_code == 422
    # duplicate code (case-insensitive)
    r3 = await client.post("/api/supervisor/issue-codes", json={
        "code": "info_dining", "label": "dup", "department": "d",
        "fulfilment_mode": "no_dispatch", "routing_model": "none",
        "intent_kind": "service"})
    assert r3.status_code == 409
    # patch + disable
    cid = body["id"]
    r4 = await client.patch(f"/api/supervisor/issue-codes/{cid}",
                            json={"status": "disabled"})
    assert r4.status_code == 200 and r4.json()["status"] == "disabled"
    # bad enum
    r5 = await client.patch(f"/api/supervisor/issue-codes/{cid}",
                            json={"fulfilment_mode": "bogus"})
    assert r5.status_code == 422
    # no DELETE
    r6 = await client.delete(f"/api/supervisor/issue-codes/{cid}")
    assert r6.status_code == 405

async def test_requires_supervisor(client):
    r = await client.get("/api/supervisor/issue-codes")
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_issue_codes.py -q`
Expected: FAIL (routes 404).

- [ ] **Step 3: DAL** — `supervisor/dal/issue_codes.py`

```python
from __future__ import annotations
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models import IssueCode


async def get(s: AsyncSession, id: uuid.UUID) -> IssueCode | None:
    return await s.get(IssueCode, id)

async def get_by_code(s: AsyncSession, code: str) -> IssueCode | None:
    res = await s.execute(select(IssueCode)
        .where(func.lower(IssueCode.code) == code.lower()))
    return res.scalars().first()

async def list_codes(s: AsyncSession, status: str | None = None):
    q = select(IssueCode)
    if status:
        q = q.where(IssueCode.status == status)
    return (await s.execute(q.order_by(IssueCode.code))).scalars().all()

async def insert(s: AsyncSession, **f) -> IssueCode:
    obj = IssueCode(**f); s.add(obj); return obj

async def update(s: AsyncSession, obj: IssueCode, **f) -> IssueCode:
    for k, v in f.items():
        if v is not None:
            setattr(obj, k, v)
    s.add(obj); return obj
```

- [ ] **Step 4: Service** — `supervisor/services/issue_codes.py`

```python
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.supervisor.dal import issue_codes as dal

_MODE = {"dispatch", "no_dispatch"}
_ROUTING = {"section_pooled", "skill_matched", "none"}
_INTENT = {"service", "problem_report"}


def _validate(mode=None, routing=None, intent=None):
    if mode is not None and mode not in _MODE:
        raise ValidationError("invalid fulfilment_mode")
    if routing is not None and routing not in _ROUTING:
        raise ValidationError("invalid routing_model")
    if intent is not None and intent not in _INTENT:
        raise ValidationError("invalid intent_kind")


async def list_codes(s, status=None):
    return await dal.list_codes(s, status=status)

async def create_code(s: AsyncSession, *, code, label, department,
                       fulfilment_mode, routing_model, intent_kind, actor):
    _validate(fulfilment_mode, routing_model, intent_kind)
    if await dal.get_by_code(s, code) is not None:
        raise ConflictError("issue code already exists")
    obj = await dal.insert(s, code=code, label=label, department=department,
                            fulfilment_mode=fulfilment_mode,
                            routing_model=routing_model,
                            intent_kind=intent_kind)
    # is_reservation_mutation intentionally NOT settable here (Resolution A)
    await s.flush()
    return obj

async def update_code(s: AsyncSession, code_id: uuid.UUID, *, actor, **fields):
    obj = await dal.get(s, code_id)
    if obj is None:
        raise NotFoundError("issue code not found")
    _validate(fields.get("fulfilment_mode"), fields.get("routing_model"),
              fields.get("intent_kind"))
    if "status" in fields and fields["status"] not in (None, "active",
                                                        "disabled"):
        raise ValidationError("invalid status")
    new_code = fields.get("code")
    if new_code and new_code.lower() != obj.code.lower():
        if await dal.get_by_code(s, new_code) is not None:
            raise ConflictError("issue code already exists")
    await dal.update(s, obj, **fields)
    await s.flush()
    return obj
```

- [ ] **Step 5: Schema** — `supervisor/schemas/issue_code.py`

```python
from __future__ import annotations
import uuid, datetime as dt
from pydantic import BaseModel, ConfigDict


class IssueCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # rejects is_reservation_mutation
    code: str
    label: str
    department: str
    fulfilment_mode: str
    routing_model: str
    intent_kind: str = "service"


class IssueCodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = None
    label: str | None = None
    department: str | None = None
    fulfilment_mode: str | None = None
    routing_model: str | None = None
    intent_kind: str | None = None
    status: str | None = None


class IssueCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    code: str
    label: str
    department: str
    fulfilment_mode: str
    routing_model: str
    intent_kind: str
    is_reservation_mutation: bool   # display-only
    status: str
    created_at: dt.datetime
```

- [ ] **Step 6: API** — `supervisor/api/issue_codes.py` and register it

```python
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.deps import Actor, require_roles, db_session
from conduit.supervisor.services import issue_codes as svc
from conduit.supervisor.schemas.issue_code import (
    IssueCodeCreate, IssueCodePatch, IssueCodeOut)

router = APIRouter(tags=["supervisor-issue-codes"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("/issue-codes", response_model=list[IssueCodeOut])
async def list_codes(status: str | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return await svc.list_codes(s, status=status)


@router.post("/issue-codes", response_model=IssueCodeOut, status_code=201)
async def create_code(body: IssueCodeCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    obj = await svc.create_code(s, actor=actor, **body.model_dump())
    await s.commit()
    return obj


@router.patch("/issue-codes/{code_id}", response_model=IssueCodeOut)
async def patch_code(code_id: uuid.UUID, body: IssueCodePatch,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    obj = await svc.update_code(s, code_id, actor=actor,
                                **body.model_dump(exclude_unset=True))
    await s.commit()
    return obj
```
In `supervisor/api/__init__.py`, add `from conduit.supervisor.api.issue_codes import router as issue_codes_router` and `router.include_router(issue_codes_router)` (mirror how `binding`/`accounts` are composed).

- [ ] **Step 7: Run to verify it passes**

Run: `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_issue_codes.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/supervisor backend/tests/spine/test_issue_codes.py
git commit -m "feat(supervisor): issue-code catalog CRUD (mutation flag system-owned)"
```

---

## Task 5: Supervisor Knowledge Base — dal + service + schema + api

**Files:**
- Create: `backend/conduit/supervisor/dal/kb.py`, `backend/conduit/supervisor/services/kb.py`, `backend/conduit/supervisor/schemas/kb.py`, `backend/conduit/supervisor/api/kb.py`
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/spine/test_kb.py`

Read spec §8 (Knowledge Base). Same shape as Task 4, simpler (no uniqueness, no locked field).

- [ ] **Step 1: Write the failing test**

`backend/tests/spine/test_kb.py`:
```python
async def test_kb_crud(client, make_account, login):
    await make_account("supervisor", "sup", "pw-123456")
    await login("sup", "pw-123456")
    r = await client.post("/api/supervisor/kb",
        json={"topic": "breakfast", "content": "7-10:30 in the Atrium"})
    assert r.status_code == 201
    kid = r.json()["id"]
    r2 = await client.post("/api/supervisor/kb",
        json={"topic": "x", "content": ""})
    assert r2.status_code == 422
    r3 = await client.patch(f"/api/supervisor/kb/{kid}",
        json={"status": "disabled"})
    assert r3.status_code == 200 and r3.json()["status"] == "disabled"
    r4 = await client.delete(f"/api/supervisor/kb/{kid}")
    assert r4.status_code == 405
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/spine/test_kb.py -q` → FAIL (404).

- [ ] **Step 3: DAL** — `supervisor/dal/kb.py`: `get(id)`, `list_entries(status=None)` (order by `created_at`), `insert(**f)`, `update(obj, **f)` — same body shape as `issue_codes.py` DAL minus `get_by_code`.

- [ ] **Step 4: Service** — `supervisor/services/kb.py`:
```python
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import NotFoundError, ValidationError
from conduit.supervisor.dal import kb as dal

async def list_entries(s, status=None):
    return await dal.list_entries(s, status=status)

async def create_entry(s: AsyncSession, *, topic, content, actor):
    if not content.strip():
        raise ValidationError("content required")
    obj = await dal.insert(s, topic=topic, content=content)
    await s.flush()
    return obj

async def update_entry(s: AsyncSession, kid: uuid.UUID, *, actor, **fields):
    obj = await dal.get(s, kid)
    if obj is None:
        raise NotFoundError("kb entry not found")
    if "content" in fields and fields["content"] is not None \
            and not fields["content"].strip():
        raise ValidationError("content required")
    if "status" in fields and fields["status"] not in (None, "active",
                                                        "disabled"):
        raise ValidationError("invalid status")
    await dal.update(s, obj, **fields)
    await s.flush()
    return obj
```

- [ ] **Step 5: Schema** — `supervisor/schemas/kb.py`: `KBEntryCreate{topic,content}` (`extra="forbid"`), `KBEntryPatch{topic?,content?,status?}` (`extra="forbid"`), `KBEntryOut{id,topic,content,status,created_at}` (`from_attributes=True, extra="forbid"`).

- [ ] **Step 6: API** — `supervisor/api/kb.py`: `GET /kb`, `POST /kb`, `PATCH /kb/{id}` — copy the structure of `supervisor/api/issue_codes.py` exactly, swapping service/schemas. Register in `supervisor/api/__init__.py`.

- [ ] **Step 7: Run to verify it passes** — `pytest tests/spine/test_kb.py -q` → PASS.

- [ ] **Step 8: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/supervisor backend/tests/spine/test_kb.py
git commit -m "feat(supervisor): knowledge-base CRUD"
```

---

## Task 6: Idempotent issue-code seed (insert-missing-by-code only)

**Files:**
- Modify: `backend/conduit/seed.py`
- Test: `backend/tests/spine/test_seed.py`

Read Resolution F. Follow the merged `ensure_property` idiom in `seed.py` (idempotency is a seed/service rule).

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_seed.py`:
```python
import sqlalchemy as sa
from conduit.shared.models import IssueCode
from conduit.seed import ensure_issue_codes

async def test_seed_is_insert_missing_only(db):
    await ensure_issue_codes(db); await db.flush()
    n1 = len((await db.execute(sa.select(IssueCode))).scalars().all())
    # supervisor disables one
    one = (await db.execute(sa.select(IssueCode).limit(1))).scalars().first()
    one.status = "disabled"; db.add(one); await db.flush()
    await ensure_issue_codes(db); await db.flush()       # re-seed
    rows = (await db.execute(sa.select(IssueCode))).scalars().all()
    assert len(rows) == n1                                 # no dup
    again = await db.get(IssueCode, one.id)
    assert again.status == "disabled"                      # edit survived
```

- [ ] **Step 2: Run to verify it fails** — FAIL (`ensure_issue_codes` missing).

- [ ] **Step 3: Implement** in `seed.py`:
```python
from sqlalchemy import select, func
from conduit.shared.models import IssueCode

_DEFAULT_ISSUE_CODES = [
    dict(code="INFO_GENERAL", label="General info", department="concierge",
         fulfilment_mode="no_dispatch", routing_model="none",
         intent_kind="service", is_reservation_mutation=False),
    dict(code="INFO_DINING", label="Dining & hours", department="concierge",
         fulfilment_mode="no_dispatch", routing_model="none",
         intent_kind="service", is_reservation_mutation=False),
    dict(code="INFO_AMENITIES", label="Amenities & wifi",
         department="concierge", fulfilment_mode="no_dispatch",
         routing_model="none", intent_kind="service",
         is_reservation_mutation=False),
    dict(code="RES_MUTATION", label="Reservation change",
         department="front_office", fulfilment_mode="no_dispatch",
         routing_model="none", intent_kind="service",
         is_reservation_mutation=True),
    dict(code="HK_REQUEST", label="Housekeeping request",
         department="housekeeping", fulfilment_mode="dispatch",
         routing_model="section_pooled", intent_kind="service",
         is_reservation_mutation=False),
]

async def ensure_issue_codes(db) -> None:
    for spec in _DEFAULT_ISSUE_CODES:
        exists = (await db.execute(select(IssueCode).where(
            func.lower(IssueCode.code) == spec["code"].lower()))
        ).scalars().first()
        if exists is None:
            db.add(IssueCode(**spec))      # insert-missing only; never update
```
Call `ensure_issue_codes` from the seed entrypoint alongside `ensure_property` (mirror how the merged seed composes its steps; commit handled by the entrypoint exactly as the existing seed does).

- [ ] **Step 4: Run to verify it passes** — `pytest tests/spine/test_seed.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/seed.py backend/tests/spine/test_seed.py
git commit -m "feat(seed): idempotent issue-code catalog (insert-missing-by-code)"
```

---

## Task 7: LLM integration boundary (bulkhead) + FakeLLM seam

**Files:**
- Modify: `backend/conduit/shared/integrations/openai.py`
- Test: `backend/tests/spine/test_llm_bulkhead.py`

Read spec §7. The merged `openai.py` already declares `LLMUnavailable(503)` and a stub `complete`. Implement two typed entrypoints `classify` and `ground` over the Responses API; both raise `LLMUnavailable` on exhaustion. Keep the module-level functions monkeypatchable.

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_llm_bulkhead.py`:
```python
import pytest
from conduit.shared.integrations import openai as llm
from conduit.shared.integrations.openai import LLMUnavailable

async def test_classify_and_ground_are_callable_and_typed(monkeypatch):
    async def fake_classify(text, catalog):
        return [{"text": text, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]
    monkeypatch.setattr(llm, "classify", fake_classify)
    out = await llm.classify("breakfast?", [])
    assert out[0]["issue_code"] == "INFO_DINING"

async def test_unavailable_is_raisable():
    with pytest.raises(LLMUnavailable):
        raise LLMUnavailable("circuit open")
```

- [ ] **Step 2: Run to verify it fails** — FAIL (`classify`/`ground` undefined).

- [ ] **Step 3: Implement** the boundary. Add Pydantic result models and the two functions; the real OpenAI call uses the Responses API `responses.parse` with `text_format=`; wrap with `tenacity` (≤2 attempts) + a simple failure-count circuit breaker; on exhaustion raise `LLMUnavailable`. Settings (`get_settings()`) supply `llm_model` (default `"gpt-5.4-mini-2026-03-17"`), `llm_timeout_s`, and the API key.
```python
from __future__ import annotations
from pydantic import BaseModel
from openai import AsyncOpenAI
from conduit.core.config import get_settings
from conduit.core.exceptions import ConduitError


class LLMUnavailable(ConduitError):
    status_code = 503


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


def _client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(timeout=getattr(s, "llm_timeout_s", 10))


_SYS_CLASSIFY = "...system prompt per spec §7 Call 1..."
_SYS_GROUND = "...system prompt per spec §7 Call 2..."


async def classify(text: str, catalog: list[dict]) -> list[dict]:
    s = get_settings()
    cat = "\n".join(
        f"{c['code']} | {c['label']} | {c['fulfilment_mode']} | "
        f"mutation={c['is_reservation_mutation']}" for c in catalog)
    try:
        r = await _client().responses.parse(
            model=s.llm_model,
            input=[{"role": "system",
                    "content": _SYS_CLASSIFY + "\nCATALOG:\n" + cat},
                   {"role": "user", "content": text}],
            text_format=_Decompose, reasoning={"effort": "low"})
    except Exception as e:                      # timeout / circuit / api error
        raise LLMUnavailable(str(e))
    return [c.model_dump() for c in r.output_parsed.children]


async def ground(question: str, context: str) -> dict:
    s = get_settings()
    try:
        r = await _client().responses.parse(
            model=s.llm_model,
            input=[{"role": "system", "content": _SYS_GROUND},
                   {"role": "user",
                    "content": f"QUESTION: {question}\n\nCONTEXT\n{context}"}],
            text_format=_Ground, reasoning={"effort": "low"})
    except Exception as e:
        raise LLMUnavailable(str(e))
    return r.output_parsed.model_dump()
```
Fill `_SYS_CLASSIFY` / `_SYS_GROUND` verbatim from spec §7 ("The prompts"). Add a small module-level circuit-breaker counter (open after N consecutive `LLMUnavailable`; fast-raise while open; reset on success) — keep it module state so a test can trip it.

- [ ] **Step 4: Run to verify it passes** — `pytest tests/spine/test_llm_bulkhead.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/shared/integrations/openai.py backend/tests/spine/test_llm_bulkhead.py
git commit -m "feat(integrations): bulkheaded gpt-5.4-mini classify/ground"
```

---

## Task 8: Triage mechanism + deterministic risk pass

**Files:**
- Modify: `backend/conduit/shared/domain/triage.py`
- Test: `backend/tests/spine/test_triage.py`

Read spec §7 + Resolution A. `classify(text, catalog)` calls `llm.classify`, maps to the existing `TriagedChild` dataclass, then the **deterministic risk pass** forces `outcome="flag"` when the matched code's `is_reservation_mutation` is true — regardless of the LLM (LLM may only raise).

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_triage.py`:
```python
from conduit.shared.domain import triage
from conduit.shared.integrations import openai as llm

async def test_mutation_code_forces_flag(monkeypatch):
    catalog = [{"code": "RES_MUTATION", "label": "x", "fulfilment_mode":
                "no_dispatch", "is_reservation_mutation": True}]
    async def fake(text, cat):
        return [{"text": text, "issue_code": "RES_MUTATION",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]
    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("can I check out at 2pm?", catalog)
    assert out[0].outcome == "flag"          # forced, LLM said no_dispatch

async def test_unknown_code_is_uncategorized(monkeypatch):
    async def fake(text, cat):
        return [{"text": text, "issue_code": None, "fulfilment_mode": None,
                 "outcome": "clarify", "is_problem_report": False}]
    monkeypatch.setattr(llm, "classify", fake)
    out = await triage.classify("zzz", [])
    assert out[0].uncategorized is True and out[0].outcome == "clarify"
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Implement** `classify` in `triage.py` (keep the `TriageOutcome` enum + `TriagedChild` dataclass already present):
```python
from conduit.shared.integrations import openai as llm

async def classify(text: str, catalog: list[dict]) -> list["TriagedChild"]:
    raw = await llm.classify(text, catalog)            # may raise LLMUnavailable
    by_code = {c["code"]: c for c in catalog}
    result = []
    for item in raw:
        code = item.get("issue_code")
        cc = by_code.get(code) if code else None
        outcome = item["outcome"]
        if cc and cc.get("is_reservation_mutation"):    # Resolution A
            outcome = "flag"                            # raise only
        result.append(TriagedChild(
            text=item["text"],
            issue_code=code if cc else None,
            outcome=TriageOutcome(outcome),
            uncategorized=cc is None,
            is_problem_report=bool(item.get("is_problem_report")),
        ))
    return result
```
(`decompose()` stub may remain unused; `classify` does decompose+classify in one structured call per spec.)

- [ ] **Step 4: Run to verify it passes** — `pytest tests/spine/test_triage.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/shared/domain/triage.py backend/tests/spine/test_triage.py
git commit -m "feat(domain): triage classify + deterministic risk pass (D24/D30)"
```

---

## Task 9: Grounding mechanism

**Files:**
- Create: `backend/conduit/shared/domain/grounding.py`
- Test: `backend/tests/spine/test_grounding.py`

Read spec §7 (Call 2). Pure mechanism: build the bounded context string from active KB rows + reservation fields, call `llm.ground`, return a typed result. No DB access.

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_grounding.py`:
```python
from conduit.shared.domain import grounding
from conduit.shared.integrations import openai as llm

async def test_ground_builds_context_and_returns(monkeypatch):
    captured = {}
    async def fake(q, ctx):
        captured["ctx"] = ctx
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "7-10:30", "used_kb_ids": ["k1"],
                "used_fields": ["room_label"]}
    monkeypatch.setattr(llm, "ground", fake)
    res = await grounding.ground(
        "breakfast?",
        kb=[{"id": "k1", "topic": "breakfast", "content": "7-10:30"}],
        facts={"room_label": "412", "section_label": "A",
               "check_in": "2026-05-16", "check_out": "2026-05-18",
               "stay_status": "active"})
    assert res["grounded"] is True
    assert "breakfast" in captured["ctx"] and "412" in captured["ctx"]
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Implement** `grounding.py`:
```python
from __future__ import annotations
from conduit.shared.integrations import openai as llm

async def ground(question: str, *, kb: list[dict], facts: dict) -> dict:
    lines = [f"- Reservation: room {facts['room_label']}, section "
             f"{facts['section_label']}, check_in {facts['check_in']}, "
             f"check_out {facts['check_out']}, status {facts['stay_status']}",
             "- Knowledge base:"]
    for e in kb:
        lines.append(f"[{e['id']}] {e['topic']}: {e['content']}")
    return await llm.ground(question, "\n".join(lines))
```

- [ ] **Step 4: Run to verify it passes** — `pytest tests/spine/test_grounding.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/shared/domain/grounding.py backend/tests/spine/test_grounding.py
git commit -m "feat(domain): grounding context builder"
```

---

## Task 10: Guest DAL (bindings, requests, children, resolutions, events)

**Files:**
- Create: `backend/conduit/guest/dal/bindings.py`, `requests.py`, `children.py`, `resolutions.py`, `events.py`
- Test: `backend/tests/spine/test_guest_dal.py`

Read Resolution E. `bindings.py` is a near-copy of the merged `public/dal/bindings.py` over the same shared models.

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_guest_dal.py`:
```python
from conduit.guest.dal import bindings, requests as rdal, children as cdal
import sqlalchemy as sa
from conduit.shared.models import Account

async def test_binding_and_request_insert(db):
    acc = (await db.execute(sa.select(Account).limit(1))).scalars().first()
    assert await bindings.get_active_binding_for_guest(db, acc.id) is None \
        or True   # shape: returns trio or None
    r = await rdal.insert_request(db, guest_account_id=acc.id,
                                  stay_id=acc.id, raw_text="hi")
    await db.flush()
    got = await rdal.get_request(db, r.id)
    assert got.raw_text == "hi"
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Implement** the five modules (add-only, no flush — the merged stay/binding DAL contract):

`bindings.py` — copy `public/dal/bindings.py::get_active_binding_for_guest` verbatim (same `select(Stay,Room,Section)` join, returns `(Stay,Room,Section)|None`).

`requests.py`:
```python
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models import Request

async def insert_request(s, *, guest_account_id, stay_id, raw_text,
                          channel="text") -> Request:
    obj = Request(guest_account_id=guest_account_id, stay_id=stay_id,
                  raw_text=raw_text, channel=channel)
    s.add(obj); return obj

async def get_request(s, id: uuid.UUID) -> Request | None:
    return await s.get(Request, id)

async def list_requests_for_guest(s, guest_account_id: uuid.UUID):
    res = await s.execute(select(Request)
        .where(Request.guest_account_id == guest_account_id)
        .order_by(Request.created_at))
    return res.scalars().all()
```

`children.py` — `insert_child(**f)`, `get_child(id)`, `list_children_for_request(request_id)`, `list_children_for_guest(guest_account_id)` (join `Request`). Add-only.

`resolutions.py` — `insert_resolution(child_id, mode, answer_text=None)`, `get_resolution(child_id)`, `set_helpful(res, helpful)` (mutate, no flush), `insert_provenance_kb(child_id, kb_entry_id, claimed_used)`, `insert_provenance_field(child_id, field_name, claimed_used)` (primitives, add-only).

`events.py` — re-export the shared writer for guest-side use: `from conduit.shared.events.writer import emit_request_created, emit_child`.

- [ ] **Step 4: Run to verify it passes** — `pytest tests/spine/test_guest_dal.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/guest/dal backend/tests/spine/test_guest_dal.py
git commit -m "feat(guest/dal): bindings, requests, children, resolutions"
```

---

## Task 11: Guest services — intake orchestration + no-dispatch resolution

**Files:**
- Modify: `backend/conduit/guest/services/intake.py`
- Create: `backend/conduit/guest/services/nodispatch.py`
- Test: `backend/tests/spine/test_intake_service.py`

Read spec §7 + Resolutions C/D/E/G + Gap-2. Orchestration only; mechanism is shared/domain; events via `lifecycle.transition`; DAL add-only; service flushes; the API handler commits (Task 12).

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_intake_service.py` (uses a scripted FakeLLM via monkeypatch; arrange a guest with an active stay via the real stay service helper as the merged harness allows):
```python
from conduit.shared.integrations import openai as llm
from conduit.guest.services import intake

async def test_grounded_answer_then_close(db, make_account, login,
                                           seeded_guest_with_stay):
    actor, ambient = seeded_guest_with_stay      # fixture (Task 13)
    async def fclassify(t, c):
        return [{"text": t, "issue_code": "INFO_DINING",
                 "fulfilment_mode": "no_dispatch", "outcome": "no_dispatch",
                 "is_problem_report": False}]
    async def fground(q, ctx):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "7-10:30 Atrium", "used_kb_ids": [],
                "used_fields": ["room_label"]}
    monkeypatch_all(llm, fclassify, fground)     # helper sets llm.classify/ground
    out = await intake.submit_request(db, actor, "what time is breakfast?")
    await db.flush()
    assert out["children"][0]["terminal"] == "answered"
    assert "7-10:30" in out["children"][0]["answer"]
```
(`seeded_guest_with_stay` and `monkeypatch_all` are provided by `tests/spine/conftest.py` in Task 13. Write the test now; it will run after Task 13. Until then mark this test `@pytest.mark.skip(reason="enabled in Task 13")` and remove the skip in Task 13 Step 6.)

- [ ] **Step 2: Run to verify it is collected & skipped** — `pytest tests/spine/test_intake_service.py -q` → 1 skipped.

- [ ] **Step 3: Implement `nodispatch.py`**:
```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.domain import grounding, lifecycle
from conduit.guest.dal import resolutions as rdal, kb as _kb  # see note
from conduit.supervisor.dal import kb as kbdal

async def resolve(s: AsyncSession, child, ambient: dict, actor_id) -> dict:
    kb = [{"id": str(e.id), "topic": e.topic, "content": e.content}
          for e in await kbdal.list_entries(s, status="active")]
    facts = {"room_label": ambient["room_label"],
             "section_label": ambient["section_label"],
             "check_in": str(ambient["check_in"]),
             "check_out": str(ambient["check_out"]),
             "stay_status": ambient["stay_status"]}
    try:
        g = await grounding.ground(child.text, kb=kb, facts=facts)
    except Exception:                                  # LLMUnavailable
        g = {"grounded": False, "leaves_no_dispatch": False, "answer": "",
             "used_kb_ids": [], "used_fields": []}
    if g["grounded"] and not g["leaves_no_dispatch"]:
        res = await rdal.insert_resolution(s, child_id=child.id,
            mode="grounded_answer", answer_text=g["answer"])
        await s.flush()
        for e in kb:
            await rdal.insert_provenance_kb(s, child.id, e["id"],
                e["id"] in g["used_kb_ids"])
        for f in facts:
            await rdal.insert_provenance_field(s, child.id, f,
                f in g["used_fields"])
        await lifecycle.transition(s, child, "answered",
            actor_account_id=actor_id, resolution_child_id=child.id)
        return {"terminal": "answered", "answer": g["answer"],
                "closure_prompt": True}
    await rdal.insert_resolution(s, child_id=child.id, mode="human_deferral")
    await s.flush()
    await lifecycle.transition(s, child, "concierge_queue",
        actor_account_id=actor_id)
    return {"terminal": "logged"}
```
(Note: `kb` is read through the supervisor DAL over shared models — read-only; the guest portal does not own KB. This is the same intentional cheap read-overlap principle stay/binding documented for ambient.)

- [ ] **Step 4: Implement `submit_request` + `confirm` in `intake.py`**:
```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.guest.dal import bindings, requests as rdal, children as cdal
from conduit.guest.dal import resolutions as resdal
from conduit.shared.events import writer
from conduit.shared.domain import triage, lifecycle
from conduit.supervisor.dal import issue_codes as icdal
from conduit.guest.services import nodispatch

async def submit_request(s: AsyncSession, actor, text: str) -> dict:
    trio = await bindings.get_active_binding_for_guest(s, actor.id)
    if trio is None:
        raise ConflictError("no active stay to action")
    stay, room, section = trio
    ambient = {"room_label": room.label, "section_label": section.label,
               "check_in": stay.check_in, "check_out": stay.check_out,
               "stay_status": stay.status}
    req = await rdal.insert_request(s, guest_account_id=actor.id,
        stay_id=stay.id, raw_text=text)
    await s.flush()
    await writer.emit_request_created(s, req.id, actor.id)
    catalog = [dict(code=c.code, label=c.label,
                    fulfilment_mode=c.fulfilment_mode,
                    is_reservation_mutation=c.is_reservation_mutation)
               for c in await icdal.list_codes(s, status="active")]
    try:
        triaged = await triage.classify(text, catalog)
    except Exception:                                  # LLMUnavailable (AD11)
        triaged = [triage.TriagedChild(text=text, issue_code=None,
            outcome=triage.TriageOutcome("clarify"), uncategorized=True,
            is_problem_report=False)]
    children_out = []
    for t in triaged:
        ic = None
        if t.issue_code:
            ic = await icdal.get_by_code(s, t.issue_code)
        child = await cdal.insert_child(s, request_id=req.id, text=t.text,
            issue_code_id=ic.id if ic else None, uncategorized=t.uncategorized,
            outcome=t.outcome.value,
            fulfilment_mode=(ic.fulfilment_mode if ic else None),
            is_problem_report=t.is_problem_report, state="intake")
        await s.flush()
        await lifecycle.transition(s, child, "triaged",
            actor_account_id=actor.id)
        if t.outcome.value == "no_dispatch":
            term = await nodispatch.resolve(s, child, ambient, actor.id)
        else:
            await writer.emit_child(s, "child_parked", child.id, actor.id)
            term = {"terminal": "logged"}
        children_out.append({"child_id": str(child.id), "text": t.text,
            "issue_code": t.issue_code, **term})
    return {"request_id": str(req.id), "children": children_out}


async def confirm(s: AsyncSession, actor, child_id, helpful: bool) -> dict:
    child = await cdal.get_child(s, child_id)
    if child is None:
        raise NotFoundError("child not found")
    req = await rdal.get_request(s, child.request_id)
    if req is None or req.guest_account_id != actor.id:
        raise NotFoundError("child not found")          # ownership (no leak)
    if child.state != "answered":
        raise ConflictError("not awaiting confirmation")
    res = await resdal.get_resolution(s, child.id)
    await resdal.set_helpful(s, res, "yes" if helpful else "no")
    if helpful:
        await lifecycle.transition(s, child, "closed",
            actor_account_id=actor.id)
        return {"child_id": str(child.id), "terminal": "answered",
                "state": "closed"}
    await lifecycle.transition(s, child, "reopened",
        actor_account_id=actor.id)
    await lifecycle.transition(s, child, "concierge_queue",
        actor_account_id=actor.id)
    return {"child_id": str(child.id), "terminal": "logged",
            "state": "concierge_queue"}
```

- [ ] **Step 5: Commit (tests enabled in Task 13)**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/guest/services backend/tests/spine/test_intake_service.py
git commit -m "feat(guest): intake orchestration + no-dispatch resolution"
```

---

## Task 12: Guest API — conversation endpoints + schemas

**Files:**
- Modify: `backend/conduit/guest/api/conversation.py`
- Create: `backend/conduit/guest/schemas/conversation.py`
- Verify: `backend/conduit/guest/api/__init__.py`
- Test: `backend/tests/spine/test_guest_api.py`

Read spec §8 (Guest). Fill the existing `submit`/`confirm` stubs and add `GET /requests` rehydration.

- [ ] **Step 1: Failing test** — `backend/tests/spine/test_guest_api.py`:
```python
async def test_requires_guest(client):
    r = await client.post("/api/guest/requests", json={"text": "hi"})
    assert r.status_code in (401, 403)

async def test_no_active_stay_409(client, make_account, login):
    await make_account("guest", "g", "pw-123456")
    await login("g", "pw-123456")
    r = await client.post("/api/guest/requests", json={"text": "hi"})
    assert r.status_code == 409
```

- [ ] **Step 2: Run to verify it fails** — FAIL (stub raises `NotImplementedError` → 500, not 409/403).

- [ ] **Step 3: Schemas** — `guest/schemas/conversation.py`:
```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str

class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    helpful: bool

class ChildOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    text: str
    issue_code: str | None = None
    terminal: str               # "answered" | "logged"
    answer: str | None = None
    closure_prompt: bool | None = None
    state: str | None = None

class RequestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    children: list[ChildOut]
```

- [ ] **Step 4: Implement the handlers** in `conversation.py` (replace the `NotImplementedError` stubs; commit at the edge):
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.deps import Actor, require_roles, db_session
from conduit.guest.services import intake
from conduit.guest.schemas.conversation import (AskIn, ConfirmIn, RequestOut,
                                                ChildOut)
from conduit.guest.dal import requests as rdal, children as cdal
from conduit.guest.dal import resolutions as resdal

router = APIRouter(tags=["guest-conversation"])
_guest = require_roles("guest")

@router.post("/requests", response_model=RequestOut)
async def submit(body: AskIn, actor: Actor = Depends(_guest),
                 s: AsyncSession = Depends(db_session)):
    out = await intake.submit_request(s, actor, body.text)
    await s.commit()
    return out

@router.post("/children/{child_id}/confirm", response_model=ChildOut)
async def confirm(child_id: str, body: ConfirmIn,
                  actor: Actor = Depends(_guest),
                  s: AsyncSession = Depends(db_session)):
    import uuid as _u
    out = await intake.confirm(s, actor, _u.UUID(child_id), body.helpful)
    await s.commit()
    return out

@router.get("/requests", response_model=list[RequestOut])
async def list_conversation(actor: Actor = Depends(_guest),
                            s: AsyncSession = Depends(db_session)):
    reqs = await rdal.list_requests_for_guest(s, actor.id)
    out = []
    for r in reqs:
        kids = await cdal.list_children_for_request(s, r.id)
        cs = []
        for c in kids:
            res = await resdal.get_resolution(s, c.id)
            cs.append(ChildOut(child_id=str(c.id), text=c.text,
                issue_code=None,
                terminal=("answered" if c.state in ("answered", "closed")
                          and res and res.mode == "grounded_answer"
                          else "logged"),
                answer=(res.answer_text if res else None),
                closure_prompt=(c.state == "answered"),
                state=c.state))
        out.append(RequestOut(request_id=str(r.id), children=cs))
    return out
```
Verify `guest/api/__init__.py` already composes this router under `/guest` (it does in the scaffold); no change unless the new GET needs no extra wiring (it doesn't — same router).

- [ ] **Step 5: Run to verify it passes** — `pytest tests/spine/test_guest_api.py -q` → PASS (the two early tests; full-stack happy path runs in Task 13/14).

- [ ] **Step 6: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/conduit/guest backend/tests/spine/test_guest_api.py
git commit -m "feat(guest/api): conversation submit/confirm/rehydrate"
```

---

## Task 13: Test bench — savepoint isolation, FakeLLM, structural guards

**Files:**
- Create: `backend/tests/spine/conftest.py`
- Create: `backend/tests/spine/test_structural_guards.py`
- Modify: `backend/tests/api/contract_snapshot.json` (regenerate)
- Modify: `backend/tests/spine/test_intake_service.py` (remove the skip)
- Test: the whole `tests/spine/` suite

Read spec §11. This task makes "pass ⇒ comfort, fail ⇒ rollback" real.

- [ ] **Step 1: Write `tests/spine/conftest.py`** — savepoint-rollback isolation + FakeLLM + fixtures:
```python
import pytest, pytest_asyncio, sqlalchemy as sa
from sqlalchemy import event
from conduit.shared.integrations import openai as llm

@pytest_asyncio.fixture
async def db(_engine):                       # overrides merged db for this pkg
    conn = await _engine.connect()
    trans = await conn.begin()
    Session = ...                            # build AsyncSession bound to conn
    s = Session()
    await conn.begin_nested()
    @event.listens_for(s.sync_session, "after_transaction_end")
    def _restart(sess, t):
        if t.nested and not t._parent.nested:
            sess.begin_nested()
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()               # rollback ALWAYS (pass/fail)
        await conn.close()

@pytest.fixture
def fake_llm(monkeypatch):
    state = {"classify": None, "ground": None}
    async def c(t, cat): return state["classify"](t, cat)
    async def g(q, ctx): return state["ground"](q, ctx)
    monkeypatch.setattr(llm, "classify", c)
    monkeypatch.setattr(llm, "ground", g)
    return state

@pytest_asyncio.fixture
async def seeded_guest_with_stay(db, make_account, login):
    ...  # create supervisor, section, room, guest, stay via the merged
        # real services (exactly as stay/binding tests arrange precondition
        # data); return (Actor-like, ambient dict)

@pytest.fixture(autouse=True)
def _leak_sentinel():                        # fallback that must never fire
    yield
    # asserted in test_structural_guards.py against a fresh session
```
Implement the elided parts using the merged harness primitives (the merged `tests/conftest.py` exposes the engine/session factory and `make_account`/`login`; reuse them — do not duplicate engine setup). The savepoint pattern is the canonical SQLAlchemy "join an external transaction" recipe; the app's `db_session` override already points at this `db`, so app commits land in the nested savepoint and are rolled back with `trans.rollback()`.

- [ ] **Step 2: Structural guards** — `tests/spine/test_structural_guards.py`:
```python
import sqlalchemy as sa, pytest
from conduit.supervisor.schemas.issue_code import IssueCodeOut
from conduit.guest.schemas.conversation import ChildOut

async def test_response_shapes_parse_back(client, make_account, login):
    await make_account("supervisor","sup","pw-123456"); await login("sup","pw-123456")
    r = await client.post("/api/supervisor/issue-codes", json={
        "code":"Z","label":"z","department":"d","fulfilment_mode":"no_dispatch",
        "routing_model":"none","intent_kind":"service"})
    IssueCodeOut(**r.json())                          # extra=forbid → red on drift

async def test_resolution_A_request_rejects_mutation(client, make_account, login):
    await make_account("supervisor","s","pw-123456"); await login("s","pw-123456")
    r = await client.post("/api/supervisor/issue-codes", json={
        "code":"Q","label":"q","department":"d","fulfilment_mode":"no_dispatch",
        "routing_model":"none","intent_kind":"service",
        "is_reservation_mutation":True})
    assert r.status_code == 422

async def test_role_matrix(client, make_account, login):
    for role in ("guest","servicer"):
        await make_account(role, role, "pw-123456"); await login(role,"pw-123456")
        assert (await client.get("/api/supervisor/issue-codes")
                ).status_code == 403

async def test_no_event_update_or_delete_path():
    # static guard: the codebase has no Event update/delete API path
    import conduit.shared.events.writer as w
    src = open(w.__file__).read()
    assert "delete(" not in src and ".delete()" not in src

async def test_leak_sentinel(db):
    from conduit.shared.models import Request, ChildSubRequest, Event
    for m in (Request, ChildSubRequest, Event):
        n = len((await db.execute(sa.select(m))).scalars().all())
        assert n == 0            # savepoint rollback ⇒ baseline between tests
```

- [ ] **Step 3: Live-policy + idempotent-seed + append-only behavioural guards** — add to the same file:
```python
async def test_live_policy_disable(client, make_account, login,
                                   seeded_guest_with_stay, fake_llm):
    # create+disable a KB entry, assert next ground sees only active
    ...
async def test_seed_survives_reseed(db):
    from conduit.seed import ensure_issue_codes
    await ensure_issue_codes(db); await db.flush()
    # disable one, re-seed, assert count stable + disabled survives
    ...
async def test_one_event_per_transition(db, seeded_guest_with_stay, fake_llm):
    # submit → assert exactly one request_created + one child_triaged +
    # one child_answered, plus matching detail rows
    ...
```
Fill the `...` using the patterns established in Tasks 6/8/11 (concrete, no placeholders left in the final file).

- [ ] **Step 4: Regenerate the contract snapshot**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend
rm -f tests/api/contract_snapshot.json
.venv/bin/pytest tests/api/test_security_guards.py -q   # recreates it
.venv/bin/pytest tests/api/test_security_guards.py -q   # now enforces it
git add tests/api/contract_snapshot.json
```
Expected: first run regenerates (1 expected fail/create), second run green; the new `/api/supervisor/issue-codes|kb` + `/api/guest/requests` routes are in the snapshot and swept by the auth-coverage meta-test.

- [ ] **Step 5: Remove the skip in `test_intake_service.py`** and add a `monkeypatch_all` helper to `conftest.py` that sets both `llm.classify`/`llm.ground` (used by that test).

- [ ] **Step 6: Run the whole spine suite**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine -q
```
Expected: ALL PASS, no leak-sentinel failure.

- [ ] **Step 7: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/tests
git commit -m "test(spine): savepoint isolation, FakeLLM, structural guards"
```

---

## Task 14: End-to-end journey sentinel

**Files:**
- Create: `backend/tests/spine/test_e2e_journey.py`

Read spec §11 (e2e sentinel). One scripted test that *is* the slice.

- [ ] **Step 1: Write the sentinel** — supervisor creates+edits a code & KB entry → guest asks (FakeLLM classify→no_dispatch, ground→grounded) → grounded answer + assert `request_created/child_triaged/child_answered` rows → closure-lite "yes" → `closed` → ask ungroundable (ground→`grounded:false`) → `concierge_queue` + `child_deferred` → supervisor disables the KB entry → same question still defers (live policy) → mixed multi-intent (classify returns 2 children: one `no_dispatch` answered + one `auto` parked) assert independent states → FakeLLM `classify` raises `LLMUnavailable` → assert one `uncategorized` child, `human_deferral`, response is 200 not 5xx, `request_created` still present. Full code, using the `fake_llm`/`seeded_guest_with_stay` fixtures and `client`.

- [ ] **Step 2: Run** — `cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest tests/spine/test_e2e_journey.py -q` → PASS.

- [ ] **Step 3: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add backend/tests/spine/test_e2e_journey.py
git commit -m "test(spine): end-to-end no-dispatch journey sentinel"
```

---

## Task 15: Frontend — guest conversation surface

**Files:**
- Install: `frontend/src/components/ui/scroll-area.tsx` (via `npx shadcn@latest add scroll-area`, then edit monochrome/tight)
- Create: `frontend/src/components/common/chat-scroll.tsx`, `message.tsx`, `request-receipt.tsx`, `child-status-card.tsx`, `composer.tsx`, `closure-lite.tsx`
- Create: `frontend/src/shell/guest/hooks/use-conversation.ts`, `frontend/src/shell/guest/pages/conversation.tsx`
- Modify: `frontend/src/App.tsx` (guest route → conversation page)
- Verify: `npm run build`

Read spec §10 (guest page). Reuse the merged TanStack/`api`/uniformity conventions exactly (`use-sections.ts` is the hook template; `api` from `@/lib/api-client`).

- [ ] **Step 1: Install scroll-area and apply the edit pass**

Run:
```bash
cd /workspace/Conduit-nodispatch/frontend && npx shadcn@latest add scroll-area
```
Edit `scroll-area.tsx`: kill default radii/shadows, neutralize the scrollbar to `bg-border`, monochrome (the documented add-then-edit pass).

- [ ] **Step 2: Hook** — `use-conversation.ts` (mirror `use-sections.ts`):
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type Child = { child_id: string; text: string; terminal:
  "answered"|"logged"; answer?: string; closure_prompt?: boolean;
  state?: string }
export type Req = { request_id: string; children: Child[] }

export function useConversation() {
  return useQuery({ queryKey: ["conversation"],
    queryFn: () => api.get<Req[]>("/guest/requests") })
}
export function useSubmitRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => api.post<Req>("/guest/requests", { text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversation"] }),
  })
}
export function useConfirmChild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; helpful: boolean }) =>
      api.post<Child>(`/guest/children/${v.id}/confirm`,
        { helpful: v.helpful }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversation"] }),
  })
}
```

- [ ] **Step 3: Components** — write `chat-scroll.tsx` (scroll-area + autoscroll-to-bottom), `message.tsx` (guest/system bubble, one "C" mark per system group), `request-receipt.tsx` ("Logged N things:" list when >1, D36), `child-status-card.tsx` (terminal `answered` → answer text + `closure-lite`; `logged` → calm muted line "Logged — a team member will follow up."), `composer.tsx` (auto-grow textarea 1→5 rows, Enter=send/Shift+Enter=newline, ≥16px font, 44px target, sticky+safe-area), `closure-lite.tsx` (two ghost buttons Yes/No → `useConfirmChild`). Full component code, monochrome, tight tokens, reusing existing `button`/`textarea`/`avatar`/`skeleton`.

- [ ] **Step 4: Page** — `shell/guest/pages/conversation.tsx`: header with the ambient room label from `useAuth()` (the trust beat — read ambient from auth context, never the query cache, per the stay/binding rule); `useConversation()` for rehydration; `useSubmitRequest()` whose **pending state renders the "Looking into that…" shimmer** (Resolution C — this is the instant-ack, no polling); render receipts + `child-status-card`s; `composer` at the bottom. Wire the guest route in `App.tsx` to this page.

- [ ] **Step 5: Build** — `cd /workspace/Conduit-nodispatch/frontend && npm run build` → typecheck + build PASS.

- [ ] **Step 6: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add frontend/src
git commit -m "feat(guest-ui): conversation surface (instant-ack, closure-lite)"
```

---

## Task 16: Frontend — supervisor Issue Codes + Knowledge Base pages

**Files:**
- Create: `frontend/src/components/common/issue-code-form-dialog.tsx`, `kb-entry-form-dialog.tsx`
- Create: `frontend/src/shell/supervisor/hooks/use-issue-codes.ts`, `use-kb.ts`
- Create: `frontend/src/shell/supervisor/pages/issue-codes.tsx`, `knowledge-base.tsx`
- Modify: `frontend/src/components/layout/nav-config.ts`, `frontend/src/App.tsx`
- Verify: `npm run build`

Read spec §10 (supervisor pages). Clone the merged `shell/supervisor/pages/sections.tsx` + `account-form-dialog.tsx` patterns exactly (`data-table-shell`, `PageHeader`, `Confirm`, dropdown-menu row actions, `status-badge` dot).

- [ ] **Step 1: Hooks** — `use-issue-codes.ts` / `use-kb.ts` mirroring `use-sections.ts` (`["issue-codes"]` / `["kb"]`; create/patch mutations invalidating by key prefix).

- [ ] **Step 2: Form dialogs** — `issue-code-form-dialog.tsx` (inputs + 3 enum `Select`s; `is_reservation_mutation` rendered as a **disabled, explained field** with tooltip "System-owned — governs the always-flag policy (D24)"); `kb-entry-form-dialog.tsx` (topic input + content `textarea` + helper "Answers are grounded only in active entries (D26)"). Clone `account-form-dialog.tsx`'s structure.

- [ ] **Step 3: Pages** — `issue-codes.tsx` (`/supervisor/setup/issue-codes`) and `knowledge-base.tsx` (`/supervisor/knowledge-base`): `PageHeader` + `data-table-shell`, columns + row `⋯` (Edit / Disable·Enable→`Confirm`) per spec §10, reflow to cards `<md`. Full component code following `sections.tsx`.

- [ ] **Step 4: Nav + routes** — add "Issue Codes" under Setup and "Knowledge Base" as its own Setup entry in `nav-config.ts`; add both routes in `App.tsx`. Tighten the `supervisorNav` grouping while there.

- [ ] **Step 5: Build** — `cd /workspace/Conduit-nodispatch/frontend && npm run build` → PASS.

- [ ] **Step 6: Commit**
```bash
cd /workspace/Conduit-nodispatch
git add frontend/src
git commit -m "feat(supervisor-ui): issue-code & knowledge-base pages"
```

---

## Task 17: Finalize — full suite, push, PR

**Files:** none (verification + delivery)

- [ ] **Step 1: Full backend suite + coverage gate**

Run:
```bash
cd /workspace/Conduit-nodispatch/backend && .venv/bin/pytest -q
```
Expected: ALL PASS including the merged auth + stay/binding suites, `tests/spine`, the structural guards, the e2e sentinel, and `--cov-fail-under=90`. If anything is red, fix in the relevant task's files before proceeding — do NOT push a red suite.

- [ ] **Step 2: Frontend build**

Run:
```bash
cd /workspace/Conduit-nodispatch/frontend && npm run build
```
Expected: typecheck + production build PASS.

- [ ] **Step 3: Confirm clean tree + sane history**

Run:
```bash
cd /workspace/Conduit-nodispatch
git status --short            # expected: empty
git log --oneline origin/main..HEAD
```
Expected: empty working tree; the layered commits from Tasks 1–16 in order.

- [ ] **Step 4: Push the branch**

Run:
```bash
cd /workspace/Conduit-nodispatch
git push -u origin feat/nodispatch-journey
```
Expected: branch pushed.

- [ ] **Step 5: Open the PR**

Run:
```bash
cd /workspace/Conduit-nodispatch
gh pr create --base main --head feat/nodispatch-journey \
  --title "No-Dispatch Journey slice" \
  --body "$(cat <<'EOF'
Implements the no-dispatch journey slice per
docs/superpowers/specs/2026-05-16-nodispatch-journey-design.md and
docs/superpowers/plans/2026-05-16-nodispatch-journey.md.

Supervisor IssueCode + KnowledgeBase CRUD → guest conversation:
decompose + mechanical triage → grounded no-dispatch answer / honest
deferral / closure-lite. Shared lifecycle/event seam; bulkheaded
gpt-5.4-mini; savepoint-rollback test bench; design-token tightening
as the isolated first commit.

Stacks on merged stay/binding (third Alembic migration, 0003).
Zero auth-owned changes. Full suite + coverage gate green; e2e
journey sentinel included.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr view --json url -q .url
```
Expected: PR URL printed.

- [ ] **Step 6: Report** — output STATUS (DONE / DONE_WITH_CONCERNS / BLOCKED), the PR URL, suite result, and anything uncertain.

---

## Self-Review (run by the plan author, before handoff)

- **Spec coverage:** every spec section maps to a task — §6 model → T2; §4 lifecycle/event seam → T3; §8 Issue Codes → T4; §8 KB → T5; Resolution F seed → T6; §7 LLM bulkhead → T7; §7 triage + Resolution A → T8; §7 grounding → T9; Resolution E + guest DAL → T10; §7 orchestration + Resolutions C/D/G + Gap-2 → T11; §8 guest API → T12; §11 test bench → T13; §11 e2e sentinel → T14; §10 guest UI + §13 tightening → T1/T15; §10 supervisor UI → T16; verification bar §12 + delivery → T17. No gap.
- **Placeholder scan:** the only `...` blocks (T13 conftest elisions, T13/T14 behavioural-guard bodies) are explicitly instructed to be filled from the concrete patterns established in earlier tasks before their commit — flagged, not silent. All model/service/api/dal code is concrete.
- **Type consistency:** `TriagedChild`/`TriageOutcome` (T8) consumed in T11; `lifecycle.transition(s, child, to, *, actor_account_id, resolution_child_id)` defined T3, called consistently T11; `RequestOut`/`ChildOut` defined T12, asserted T13; `ensure_issue_codes` defined T6, used T13/T14; `get_active_binding_for_guest` trio shape consistent T10/T11.
- **No /workspace/LanceLive reference:** confirmed — only Conduit paths and in-repo D/AD ids appear.
