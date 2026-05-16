# Stay / Binding Slice ("Check-in & Relocation") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Section/Room/Stay binding so a supervisor checks a guest in and the guest's session resolves ambient `{room, section, stay}`, with a supervisor-triggered mid-stay relocation that re-binds it — fully relational, append-only-audited, regression-proof.

**Architecture:** Stacks on the now-merged auth code on `main`. New relational models in `shared/models/` (only DB-touching code); supervisor portal owns binding CRUD + event writes; `public` gains one ambient read and an extended `/auth/me`. Everything is **async** (`AsyncSession`). No jsonb. No DELETE.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0 (`AsyncSession`, `Mapped`/`mapped_column`), Alembic, Postgres, pytest-asyncio + httpx ASGITransport, React 19 + TanStack Query + shadcn, Vite.

**Spec:** `docs/superpowers/specs/2026-05-16-stay-binding-design.md` (rationale + decision ledger). This plan is build steps only.

---

## Execution prerequisites (read first)

- Auth is **merged to `main`**. The worktree branches from `main`. No merge gate remains.
- **The merged codebase is fully async.** Every DAL/service/API/seed function is `async def`; DB calls are `await s.execute(...)` / `await s.get(...)`; reads end `.scalar_one_or_none()` / `(await s.execute(q)).scalars().all()`. Never write a sync `Session`.
- **DAL adds, does not flush** (auth precedent: `insert_account` is add-only). **Services `await s.flush()`** when they need a generated id (before inserting an event detail). **The API handler `await s.commit()`s** after a mutating service call (read endpoints never commit) — exactly `supervisor/api/accounts.py::create_account`.
- Domain errors in `core/exceptions.py` (`ConduitError`=400, `NotFoundError`=404, `AuthError`=401, `ForbiddenError`=403, `ConflictError`=409). This slice **adds `ValidationError`=422** (Task 2). A raw `ValueError` would 500 — never use it for a 422.
- Router pattern: a sub-router composed by `conduit/supervisor/api/__init__.py` under `APIRouter(prefix="/supervisor")`; `main.py` adds `s.api_prefix` (`/api`). Gating is **per-handler** `actor: Actor = Depends(_sup)` with `_sup = require_roles("supervisor","duty_manager")`.
- Tests are `async def` (`asyncio_mode=auto`). Fixtures in `tests/conftest.py`: `db`, `client`, `make_account`, `login`. There is **no `supervisor_client`** — an authed supervisor chain is `await make_account("supervisor","sup","pw-123456"); await login("sup","pw-123456")` then use `client`.

## File structure (decomposition locked here)

```
backend/conduit/core/exceptions.py                (modify) + ValidationError(422)
backend/conduit/shared/models/{property,section,room,stay,event}.py
backend/conduit/shared/models/__init__.py         (modify) register + __all__
backend/migrations/versions/0002_stay_binding.py
backend/conduit/supervisor/dal/{sections,rooms,stays,events}.py
backend/conduit/public/dal/bindings.py
backend/conduit/supervisor/services/{sections,rooms,stays}.py
backend/conduit/public/services/auth.py           (modify) + resolve_ambient
backend/conduit/public/schemas/auth.py            (modify) AuthUser + 5 ambient
backend/conduit/public/api/auth.py                (modify) /me builds ambient
backend/conduit/supervisor/schemas/binding.py
backend/conduit/supervisor/api/binding.py
backend/conduit/supervisor/api/__init__.py        (modify) include binding router
backend/conduit/seed.py                           (modify) ensure_property
backend/tests/binding/...                          conftest + layered + invariants + e2e
backend/tests/api/contract_snapshot.json          (regenerate by deleting)
frontend/src/components/common/{combobox-field,date-range-field}.tsx
frontend/src/shell/supervisor/hooks/{invalidate-binding,use-sections,use-rooms,use-stays}.ts
frontend/src/shell/supervisor/pages/{sections,provisioning}.tsx
frontend/src/shell/supervisor/nav.tsx             (modify)
frontend/src/App.tsx                              (modify)
```

---

# PHASE 0 — Worktree, env, preflight

### Task 0a: Worktree off main + carry docs

- [ ] **Step 1: Commit plan+spec on the design branch**

```bash
cd /workspace/Conduit
git add docs/superpowers/plans/2026-05-16-stay-binding.md docs/superpowers/specs/2026-05-16-stay-binding-design.md
git commit -m "docs: stay/binding plan+spec reconciled to main" || echo "already committed"
```

- [ ] **Step 2: Create the worktree off `main`**

```bash
cd /workspace/Conduit
git worktree add -b feat/stay-binding /workspace/Conduit-stay-binding main
cd /workspace/Conduit-stay-binding && git branch --show-current   # feat/stay-binding
```

- [ ] **Step 3: Carry spec + plan into the worktree**

```bash
mkdir -p /workspace/Conduit-stay-binding/docs/superpowers/specs /workspace/Conduit-stay-binding/docs/superpowers/plans
git -C /workspace/Conduit show stay-binding-design:docs/superpowers/specs/2026-05-16-stay-binding-design.md > /workspace/Conduit-stay-binding/docs/superpowers/specs/2026-05-16-stay-binding-design.md
git -C /workspace/Conduit show stay-binding-design:docs/superpowers/plans/2026-05-16-stay-binding.md > /workspace/Conduit-stay-binding/docs/superpowers/plans/2026-05-16-stay-binding.md
cd /workspace/Conduit-stay-binding && git add docs/superpowers && git commit -m "docs: carry stay/binding spec + plan into worktree"
```

### Task 0b: .env + venv

- [ ] **Step 1: Copy env files**

```bash
cp /workspace/Conduit/backend/.env  /workspace/Conduit-stay-binding/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-stay-binding/frontend/.env
test -f /workspace/Conduit-stay-binding/backend/.env && test -f /workspace/Conduit-stay-binding/frontend/.env && echo "env OK"
```

- [ ] **Step 2: Seed + re-link the venv**

```bash
cp -a /workspace/Conduit/backend/.venv /workspace/Conduit-stay-binding/backend/.venv
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/pip install -e . --no-deps -q
./.venv/bin/python -c "import conduit,pathlib;print(pathlib.Path(conduit.__file__).resolve())"
# Expect a path under /workspace/Conduit-stay-binding/backend/
```

- [ ] **Step 3: Baseline — the merged suite is green**

```bash
cd /workspace/Conduit-stay-binding/backend && ./.venv/bin/pytest -q
# Expect: green (auth's merged state). If red, stop — not this slice's bug.
```

### Task 0c: Confirm conventions (sanity, not abort)

- [ ] **Step 1: Confirm the foundation is present**

```bash
cd /workspace/Conduit-stay-binding/backend
test -f conduit/shared/models/account.py && ls migrations/versions/0001_account.py \
 && grep -q "current_account" conduit/public/services/auth.py \
 && grep -q "class AuthUser" conduit/public/schemas/auth.py \
 && grep -q "make_account" tests/conftest.py \
 && test -f ../frontend/src/components/common/data-table-shell.tsx \
 && echo "foundation present — proceed"
```

- [ ] **Step 2: Note the alembic head**

```bash
./.venv/bin/alembic heads   # Expect "0001 (head)" — this slice's down_revision = "0001"
```

---

# PHASE 1 — Backend (TDD; ends fully green)

> Paths relative to `/workspace/Conduit-stay-binding/backend`. Run `./.venv/bin/pytest`.

### Task 1: Test package + binding conftest (async, FK-ordered teardown)

**Files:** Create `tests/binding/__init__.py`, `tests/binding/conftest.py`

- [ ] **Step 1: Create the package**

```python
# tests/binding/__init__.py
```

- [ ] **Step 2: Create `tests/binding/conftest.py`**

The `db` fixture's `finally` deletes only `Account`; our FK'd tables must be cleared first. This autouse fixture's `finally` runs before the `db` finalizer (pytest LIFO), so the inherited `Account` delete then succeeds.

```python
# tests/binding/conftest.py
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import delete, func, select


@pytest_asyncio.fixture(autouse=True)
async def _binding_cleanup(db):
    from conduit.shared.models.event import (
        Event, EventGuestRelocated, EventStayCreated, EventStayEnded,
    )
    from conduit.shared.models.room import Room
    from conduit.shared.models.section import Section
    from conduit.shared.models.stay import Stay
    order = [EventGuestRelocated, EventStayEnded, EventStayCreated, Event,
             Stay, Room, Section]
    try:
        yield
    finally:
        await db.rollback()
        for model in order:
            await db.execute(delete(model))
        await db.commit()
        for model in (Stay, Room, Section, Event):
            n = (await db.execute(
                select(func.count()).select_from(model))).scalar_one()
            assert n == 0, f"LEAK: {model.__tablename__} = {n}"


@pytest_asyncio.fixture()
async def seeded_property(db):
    from conduit.shared.models.property import Property
    p = (await db.execute(select(Property))).scalars().first()
    if p is None:
        p = Property(name="Test Property")
        db.add(p)
        await db.flush()
    return p
```

- [ ] **Step 3: Commit**

```bash
git add tests/binding/__init__.py tests/binding/conftest.py
git commit -m "test(binding): async FK-ordered teardown + seeded_property + leak sentinel"
```

### Task 2: Add `ValidationError` (422)

**Files:** Modify `conduit/core/exceptions.py`; Test `tests/binding/test_exceptions.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_exceptions.py
from conduit.core.exceptions import ValidationError, ConduitError


def test_validation_error_is_422_conduit_error():
    e = ValidationError("bad")
    assert isinstance(e, ConduitError)
    assert e.status_code == 422
    assert e.message == "bad"
```

- [ ] **Step 2: Run, expect fail.** `./.venv/bin/pytest tests/binding/test_exceptions.py -q` → ImportError

- [ ] **Step 3: Implement** — add after `ConflictError` in `conduit/core/exceptions.py`:

```python
class ValidationError(ConduitError):
    status_code = 422
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_exceptions.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/core/exceptions.py tests/binding/test_exceptions.py
git commit -m "feat(core): ValidationError (422)"
```

### Task 3: Models — Property, Section, Room, Stay, Event(+3 detail)

**Files:** Create `conduit/shared/models/{property,section,room,stay,event}.py`; Modify `conduit/shared/models/__init__.py`; Test `tests/binding/test_models.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_models.py
def test_models_import_and_columns():
    from conduit.shared.models.property import Property
    from conduit.shared.models.section import Section
    from conduit.shared.models.room import Room
    from conduit.shared.models.stay import Stay
    from conduit.shared.models.event import (
        Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
    )
    assert {"id", "name"} <= set(Property.__table__.columns.keys())
    assert {"id", "property_id", "label"} <= set(Section.__table__.columns)
    assert {"id", "section_id", "label"} <= set(Room.__table__.columns)
    assert {"id", "guest_account_id", "room_id", "check_in", "check_out",
            "status"} <= set(Stay.__table__.columns)
    assert {"id", "type", "actor_account_id", "at"} <= set(
        Event.__table__.columns)
    relfks = {fk.column.table.name
              for fk in EventGuestRelocated.__table__.foreign_keys}
    assert {"event", "stay", "room"} <= relfks
    assert "section" in {fk.column.table.name
                         for fk in Room.__table__.foreign_keys}
    assert {"account", "room"} <= {fk.column.table.name
                                   for fk in Stay.__table__.foreign_keys}
```

- [ ] **Step 2: Run, expect fail.** `./.venv/bin/pytest tests/binding/test_models.py -q` → ImportError

- [ ] **Step 3: Implement** (mirror `account.py`: `UUID(as_uuid=True)` pk `default=uuid.uuid4`, `server_default` for status/timestamps, `text + CheckConstraint`).

```python
# conduit/shared/models/property.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Property(Base):
    __tablename__ = "property"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

```python
# conduit/shared/models/section.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Section(Base):
    __tablename__ = "section"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

```python
# conduit/shared/models/room.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Room(Base):
    __tablename__ = "room"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

```python
# conduit/shared/models/stay.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Stay(Base):
    __tablename__ = "stay"
    __table_args__ = (
        CheckConstraint("status in ('active','ended')", name="ck_stay_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)
    check_in: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    check_out: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
```

```python
# conduit/shared/models/event.py
from __future__ import annotations
import datetime as dt, uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "type in ('stay_created','stay_ended','guest_relocated')",
            name="ck_event_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String, nullable=False)
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True)
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class EventStayCreated(Base):
    __tablename__ = "event_stay_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)


class EventStayEnded(Base):
    __tablename__ = "event_stay_ended"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)


class EventGuestRelocated(Base):
    __tablename__ = "event_guest_relocated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True)
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False)
    from_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)
    to_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False)
```

In `conduit/shared/models/__init__.py`, add imports and extend `__all__` (match the existing style — `from ... import X` then list in `__all__`):

```python
from conduit.shared.models.property import Property
from conduit.shared.models.section import Section
from conduit.shared.models.room import Room
from conduit.shared.models.stay import Stay
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)

__all__ = ["Base", "Account", "Property", "Section", "Room", "Stay",
           "Event", "EventStayCreated", "EventStayEnded",
           "EventGuestRelocated"]
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_models.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/shared/models/ tests/binding/test_models.py
git commit -m "feat(models): Property/Section/Room/Stay/Event(+3 detail)"
```

### Task 4: Migration `0002_stay_binding.py`

**Files:** Create `migrations/versions/0002_stay_binding.py`; Test `tests/binding/test_migration.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_migration.py
from sqlalchemy import inspect, text


async def test_tables_and_partial_index_exist(db):
    def _names(c):
        return set(inspect(c).get_table_names())
    names = await db.run_sync(lambda c: _names(c))
    assert {"property", "section", "room", "stay", "event",
            "event_stay_created", "event_stay_ended",
            "event_guest_relocated"} <= names
    idx = (await db.execute(text(
        "select indexname from pg_indexes where tablename='stay'"
    ))).scalars().all()
    assert "uq_stay_one_active_per_guest" in idx
```

- [ ] **Step 2: Run, expect fail.** `./.venv/bin/pytest tests/binding/test_migration.py -q` → FAIL (tables absent until Step 3 lands and the session DB rebuilds via `alembic upgrade head`)

- [ ] **Step 3: Implement** (mirror `0001_account.py`: `server_default=sa.text("gen_random_uuid()")` ids, `sa.text("now()")` timestamps; `down_revision="0001"`; FK-order create; partial unique index last).

```python
# migrations/versions/0002_stay_binding.py
"""stay binding

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _ts(col):
    return sa.Column(col, sa.DateTime(timezone=True),
                     server_default=sa.text("now()"), nullable=False)


def _pk():
    return sa.Column("id", _UUID, primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def upgrade() -> None:
    op.create_table(
        "property", _pk(),
        sa.Column("name", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "section", _pk(),
        sa.Column("property_id", _UUID,
                  sa.ForeignKey("property.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "room", _pk(),
        sa.Column("section_id", _UUID,
                  sa.ForeignKey("section.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        _ts("created_at"), _ts("updated_at"))
    op.create_table(
        "stay", _pk(),
        sa.Column("guest_account_id", _UUID,
                  sa.ForeignKey("account.id"), nullable=False),
        sa.Column("room_id", _UUID, sa.ForeignKey("room.id"),
                  nullable=False),
        sa.Column("check_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False,
                  server_default="active"),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("status in ('active','ended')",
                           name="ck_stay_status"))
    op.create_index(
        "uq_stay_one_active_per_guest", "stay", ["guest_account_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        "event", _pk(),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("actor_account_id", _UUID,
                  sa.ForeignKey("account.id"), nullable=True),
        _ts("at"),
        sa.CheckConstraint(
            "type in ('stay_created','stay_ended','guest_relocated')",
            name="ck_event_type"))
    for t, extra in (
        ("event_stay_created", []),
        ("event_stay_ended", []),
        ("event_guest_relocated", [
            sa.Column("from_room_id", _UUID,
                      sa.ForeignKey("room.id"), nullable=False),
            sa.Column("to_room_id", _UUID,
                      sa.ForeignKey("room.id"), nullable=False)]),
    ):
        op.create_table(
            t,
            sa.Column("event_id", _UUID, sa.ForeignKey("event.id"),
                      primary_key=True),
            sa.Column("stay_id", _UUID, sa.ForeignKey("stay.id"),
                      nullable=False),
            *extra)


def downgrade() -> None:
    for t in ("event_guest_relocated", "event_stay_ended",
              "event_stay_created", "event"):
        op.drop_table(t)
    op.drop_index("uq_stay_one_active_per_guest", table_name="stay")
    for t in ("stay", "room", "section", "property"):
        op.drop_table(t)
```

- [ ] **Step 4: Run the model + migration tests** (the session-scoped `conduit_test` DB rebuilds via `alembic upgrade head`, now including 0002).

Run: `./.venv/bin/pytest tests/binding/test_models.py tests/binding/test_migration.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0002_stay_binding.py tests/binding/test_migration.py
git commit -m "feat(db): 0002 stay binding migration + partial unique index"
```

### Task 5: `supervisor/dal/sections.py`

**Files:** Create `conduit/supervisor/dal/sections.py`; Test `tests/binding/test_dal_sections.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_dal_sections.py
from conduit.supervisor.dal import sections as dal


async def test_section_dal(db, seeded_property):
    s = await dal.insert_section(db, seeded_property.id, "North Wing")
    await db.flush()
    assert (await dal.get_section(db, s.id)).label == "North Wing"
    assert (await dal.get_section_by_label(
        db, seeded_property.id, "north wing")).id == s.id
    rows = await dal.list_sections_with_room_counts(db)
    assert any(sec.id == s.id and c == 0 for sec, c in rows)
    await dal.update_section(db, s, label="North")
    assert (await dal.get_section(db, s.id)).label == "North"
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement** (async; add-only, no flush — auth DAL precedent)

```python
# conduit/supervisor/dal/sections.py
from __future__ import annotations
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.room import Room
from conduit.shared.models.section import Section


async def get_section(s: AsyncSession, sid: uuid.UUID) -> Section | None:
    return await s.get(Section, sid)


async def get_section_by_label(
    s: AsyncSession, property_id: uuid.UUID, label: str
) -> Section | None:
    res = await s.execute(select(Section).where(
        Section.property_id == property_id,
        func.lower(Section.label) == label.lower()))
    return res.scalar_one_or_none()


async def list_sections_with_room_counts(
    s: AsyncSession,
) -> list[tuple[Section, int]]:
    res = await s.execute(
        select(Section, func.count(Room.id))
        .outerjoin(Room, Room.section_id == Section.id)
        .group_by(Section.id).order_by(func.lower(Section.label)))
    return [(sec, int(c)) for sec, c in res.all()]


async def insert_section(
    s: AsyncSession, property_id: uuid.UUID, label: str
) -> Section:
    sec = Section(property_id=property_id, label=label)
    s.add(sec)
    return sec


async def update_section(
    s: AsyncSession, section: Section, *, label: str
) -> Section:
    section.label = label
    s.add(section)
    return section
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_dal_sections.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/sections.py tests/binding/test_dal_sections.py
git commit -m "feat(supervisor/dal): sections (async)"
```

### Task 6: `supervisor/dal/rooms.py`

**Files:** Create `conduit/supervisor/dal/rooms.py`; Test `tests/binding/test_dal_rooms.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_dal_rooms.py
from conduit.supervisor.dal import sections as sdal, rooms as dal


async def test_room_dal(db, seeded_property):
    sec = await sdal.insert_section(db, seeded_property.id, "North")
    await db.flush()
    r = await dal.insert_room(db, sec.id, "304")
    await db.flush()
    assert (await dal.get_room(db, r.id)).label == "304"
    assert (await dal.get_room_by_label(db, "304")).id == r.id
    other = await sdal.insert_section(db, seeded_property.id, "South")
    await db.flush()
    await dal.update_room(db, r, label="305", section_id=other.id)
    got = await dal.get_room(db, r.id)
    assert got.label == "305" and got.section_id == other.id
    assert [x.id for x in await dal.list_rooms(db, other.id)] == [r.id]
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/rooms.py
from __future__ import annotations
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.room import Room


async def get_room(s: AsyncSession, rid: uuid.UUID) -> Room | None:
    return await s.get(Room, rid)


async def get_room_by_label(s: AsyncSession, label: str) -> Room | None:
    res = await s.execute(select(Room).where(
        func.lower(Room.label) == label.lower()))
    return res.scalar_one_or_none()


async def list_rooms(
    s: AsyncSession, section_id: uuid.UUID | None = None
) -> list[Room]:
    q = select(Room).order_by(func.lower(Room.label))
    if section_id is not None:
        q = q.where(Room.section_id == section_id)
    return list((await s.execute(q)).scalars().all())


async def insert_room(
    s: AsyncSession, section_id: uuid.UUID, label: str
) -> Room:
    r = Room(section_id=section_id, label=label)
    s.add(r)
    return r


async def update_room(
    s: AsyncSession, room: Room, *,
    label: str | None = None, section_id: uuid.UUID | None = None,
) -> Room:
    if label is not None:
        room.label = label
    if section_id is not None:
        room.section_id = section_id
    s.add(room)
    return room
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_dal_rooms.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/rooms.py tests/binding/test_dal_rooms.py
git commit -m "feat(supervisor/dal): rooms (async)"
```

### Task 7: `supervisor/dal/stays.py`

**Files:** Create `conduit/supervisor/dal/stays.py`; Test `tests/binding/test_dal_stays.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_dal_stays.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as dal


async def test_stay_dal(db, seeded_property, make_account):
    g = await make_account("guest", "g-dal-1")
    sec = await sdal.insert_section(db, seeded_property.id, "N")
    await db.flush()
    r = await rdal.insert_room(db, sec.id, "304")
    await db.flush()
    n = datetime.now(timezone.utc)
    st = await dal.insert_stay(db, g.id, r.id, n, n + timedelta(days=2))
    await db.flush()
    assert (await dal.get_stay(db, st.id)).id == st.id
    assert (await dal.get_active_stay_for_guest(db, g.id)).id == st.id
    await dal.set_stay_room(db, st, r.id)
    await dal.set_stay_status(db, st, "ended")
    assert await dal.get_active_stay_for_guest(db, g.id) is None
    assert st.id in [x.id for x in await dal.list_stays(db, guest_id=g.id)]
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/stays.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.stay import Stay


async def get_stay(s: AsyncSession, sid: uuid.UUID) -> Stay | None:
    return await s.get(Stay, sid)


async def get_active_stay_for_guest(
    s: AsyncSession, guest_account_id: uuid.UUID
) -> Stay | None:
    res = await s.execute(select(Stay).where(
        Stay.guest_account_id == guest_account_id,
        Stay.status == "active"))
    return res.scalar_one_or_none()


async def list_stays(
    s: AsyncSession, status: str | None = None,
    guest_id: uuid.UUID | None = None,
) -> list[Stay]:
    q = select(Stay).order_by(Stay.created_at.desc())
    if status is not None:
        q = q.where(Stay.status == status)
    if guest_id is not None:
        q = q.where(Stay.guest_account_id == guest_id)
    return list((await s.execute(q)).scalars().all())


async def insert_stay(
    s: AsyncSession, guest_account_id: uuid.UUID, room_id: uuid.UUID,
    check_in: datetime, check_out: datetime,
) -> Stay:
    st = Stay(guest_account_id=guest_account_id, room_id=room_id,
              check_in=check_in, check_out=check_out, status="active")
    s.add(st)
    return st


async def update_stay_fields(
    s: AsyncSession, stay: Stay, *,
    check_in: datetime | None = None, check_out: datetime | None = None,
) -> Stay:
    if check_in is not None:
        stay.check_in = check_in
    if check_out is not None:
        stay.check_out = check_out
    s.add(stay)
    return stay


async def set_stay_room(
    s: AsyncSession, stay: Stay, new_room_id: uuid.UUID
) -> Stay:
    stay.room_id = new_room_id
    s.add(stay)
    return stay


async def set_stay_status(
    s: AsyncSession, stay: Stay, status: str
) -> Stay:
    stay.status = status
    s.add(stay)
    return stay
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_dal_stays.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/stays.py tests/binding/test_dal_stays.py
git commit -m "feat(supervisor/dal): stays (async)"
```

### Task 8: `supervisor/dal/events.py`

**Files:** Create `conduit/supervisor/dal/events.py`; Test `tests/binding/test_dal_events.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_dal_events.py
import uuid
from sqlalchemy import select
from conduit.supervisor.dal import events as dal
from conduit.shared.models.event import Event, EventGuestRelocated


async def test_events_dal(db):
    e = await dal.insert_event(db, type="stay_created", actor_account_id=None)
    await db.flush()
    await dal.insert_stay_created(db, e.id, uuid.uuid4())
    assert (await db.get(Event, e.id)).type == "stay_created"
    e2 = await dal.insert_event(db, type="guest_relocated",
                                actor_account_id=None)
    await db.flush()
    fr, to = uuid.uuid4(), uuid.uuid4()
    await dal.insert_guest_relocated(db, e2.id, uuid.uuid4(), fr, to)
    row = (await db.execute(select(EventGuestRelocated))).scalars().one()
    assert row.from_room_id == fr and row.to_room_id == to
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/events.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.event import (
    Event, EventGuestRelocated, EventStayCreated, EventStayEnded,
)


async def insert_event(
    s: AsyncSession, *, type: str, actor_account_id: uuid.UUID | None,
) -> Event:
    e = Event(type=type, actor_account_id=actor_account_id)
    s.add(e)
    return e


async def insert_stay_created(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    s.add(EventStayCreated(event_id=event_id, stay_id=stay_id))


async def insert_stay_ended(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    s.add(EventStayEnded(event_id=event_id, stay_id=stay_id))


async def insert_guest_relocated(
    s: AsyncSession, event_id: uuid.UUID, stay_id: uuid.UUID,
    from_room_id: uuid.UUID, to_room_id: uuid.UUID,
) -> None:
    s.add(EventGuestRelocated(
        event_id=event_id, stay_id=stay_id,
        from_room_id=from_room_id, to_room_id=to_room_id))
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_dal_events.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/events.py tests/binding/test_dal_events.py
git commit -m "feat(supervisor/dal): event insert primitives (async)"
```

### Task 9: `public/dal/bindings.py` — the one ambient read

**Files:** Create `conduit/public/dal/bindings.py`; Test `tests/binding/test_dal_bindings.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_dal_bindings.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as stdal
from conduit.public.dal import bindings as dal


async def test_binding_read(db, seeded_property, make_account):
    g = await make_account("guest", "g-bind-1")
    assert await dal.get_active_binding_for_guest(db, g.id) is None
    sec = await sdal.insert_section(db, seeded_property.id, "North")
    await db.flush()
    r = await rdal.insert_room(db, sec.id, "304")
    await db.flush()
    n = datetime.now(timezone.utc)
    await stdal.insert_stay(db, g.id, r.id, n, n + timedelta(days=1))
    await db.flush()
    trio = await dal.get_active_binding_for_guest(db, g.id)
    assert trio is not None
    stay, room, section = trio
    assert room.label == "304" and section.label == "North"
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/public/dal/bindings.py
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.shared.models.room import Room
from conduit.shared.models.section import Section
from conduit.shared.models.stay import Stay


async def get_active_binding_for_guest(
    s: AsyncSession, guest_account_id: uuid.UUID
) -> tuple[Stay, Room, Section] | None:
    res = await s.execute(
        select(Stay, Room, Section)
        .join(Room, Room.id == Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(Stay.guest_account_id == guest_account_id,
               Stay.status == "active"))
    row = res.first()
    return None if row is None else (row[0], row[1], row[2])
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_dal_bindings.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/public/dal/bindings.py tests/binding/test_dal_bindings.py
git commit -m "feat(public/dal): ambient binding read (async)"
```

### Task 10: `supervisor/services/sections.py` + `rooms.py`

**Files:** Create `conduit/supervisor/services/sections.py`, `rooms.py`; Test `tests/binding/test_svc_sections_rooms.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_svc_sections_rooms.py
import uuid
import pytest
from conduit.supervisor.services import sections as ssvc, rooms as rsvc
from conduit.core.exceptions import NotFoundError, ConflictError, ValidationError


async def test_sections(db, seeded_property):
    s = await ssvc.create_section(db, seeded_property.id, "North", actor=None)
    await db.flush()
    assert any(sec.id == s.id and c == 0
               for sec, c in await ssvc.list_sections(db))
    with pytest.raises(ConflictError):
        await ssvc.create_section(db, seeded_property.id, "north", actor=None)
    with pytest.raises(NotFoundError):
        await ssvc.rename_section(db, uuid.uuid4(), "X", actor=None)


async def test_rooms(db, seeded_property):
    sec = await ssvc.create_section(db, seeded_property.id, "N", actor=None)
    await db.flush()
    r = await rsvc.create_room(db, "304", sec.id, actor=None)
    await db.flush()
    assert r.id in [x.id for x in await rsvc.list_rooms(db, sec.id)]
    with pytest.raises(ValidationError):
        await rsvc.create_room(db, "9", uuid.uuid4(), actor=None)
    with pytest.raises(ConflictError):
        await rsvc.create_room(db, "304", sec.id, actor=None)
    with pytest.raises(NotFoundError):
        await rsvc.update_room(db, uuid.uuid4(), label="X", actor=None)
    other = await ssvc.create_section(db, seeded_property.id, "S", actor=None)
    await db.flush()
    await rsvc.update_room(db, r.id, section_id=other.id, actor=None)
    assert (await rsvc.list_rooms(db, other.id))[0].id == r.id
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/services/sections.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError
from conduit.supervisor.dal import sections as dal


async def list_sections(s: AsyncSession):
    return await dal.list_sections_with_room_counts(s)


async def create_section(s: AsyncSession, property_id: uuid.UUID,
                          label: str, *, actor):
    if await dal.get_section_by_label(s, property_id, label) is not None:
        raise ConflictError("section label already exists")
    return await dal.insert_section(s, property_id, label)


async def rename_section(s: AsyncSession, section_id: uuid.UUID,
                          label: str, *, actor):
    sec = await dal.get_section(s, section_id)
    if sec is None:
        raise NotFoundError("section not found")
    dup = await dal.get_section_by_label(s, sec.property_id, label)
    if dup is not None and dup.id != sec.id:
        raise ConflictError("section label already exists")
    return await dal.update_section(s, sec, label=label)
```

```python
# conduit/supervisor/services/rooms.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.supervisor.dal import rooms as dal, sections as sdal


async def _require_section(s, section_id):
    if await sdal.get_section(s, section_id) is None:
        raise ValidationError("section does not exist")


async def list_rooms(s: AsyncSession, section_id: uuid.UUID | None = None):
    return await dal.list_rooms(s, section_id)


async def create_room(s: AsyncSession, label: str,
                        section_id: uuid.UUID, *, actor):
    await _require_section(s, section_id)
    if await dal.get_room_by_label(s, label) is not None:
        raise ConflictError("room label already exists")
    return await dal.insert_room(s, section_id, label)


async def update_room(s: AsyncSession, room_id: uuid.UUID, *,
                        label: str | None = None,
                        section_id: uuid.UUID | None = None, actor):
    room = await dal.get_room(s, room_id)
    if room is None:
        raise NotFoundError("room not found")
    if section_id is not None:
        await _require_section(s, section_id)
    if label is not None:
        dup = await dal.get_room_by_label(s, label)
        if dup is not None and dup.id != room.id:
            raise ConflictError("room label already exists")
    return await dal.update_room(s, room, label=label, section_id=section_id)
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_svc_sections_rooms.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/sections.py conduit/supervisor/services/rooms.py tests/binding/test_svc_sections_rooms.py
git commit -m "feat(supervisor/services): sections + rooms (async, ValidationError)"
```

### Task 11: `supervisor/services/stays.py`

**Files:** Create `conduit/supervisor/services/stays.py`; Test `tests/binding/test_svc_stays.py`

- [ ] **Step 1: Failing test (every guard branch + event emission)**

```python
# tests/binding/test_svc_stays.py
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import func, select
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as svc
from conduit.core.exceptions import NotFoundError, ConflictError, ValidationError
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)


async def _rooms(db, seeded_property):
    s = await ssvc.create_section(db, seeded_property.id, "N", actor=None)
    await db.flush()
    r1 = await rsvc.create_room(db, "304", s.id, actor=None)
    r2 = await rsvc.create_room(db, "511", s.id, actor=None)
    await db.flush()
    return r1, r2


def _win():
    n = datetime.now(timezone.utc)
    return n, n + timedelta(days=2)


async def test_create_emits_event(db, seeded_property, make_account):
    g = await make_account("guest", "g-s1")
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    assert st.status == "active"
    assert (await db.execute(
        select(func.count()).select_from(EventStayCreated))).scalar_one() == 1
    assert (await db.execute(select(Event))).scalars().one().type \
        == "stay_created"


async def test_create_guards(db, seeded_property, make_account):
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    sup = await make_account("supervisor", "s-bad")
    with pytest.raises(ValidationError):
        await svc.create_stay(db, sup.id, r1.id, ci, co, actor=None)
    g = await make_account("guest", "g-s2")
    with pytest.raises(ValidationError):
        await svc.create_stay(db, g.id, uuid.uuid4(), ci, co, actor=None)
    await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    with pytest.raises(ConflictError):
        await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)


async def test_update_benign_no_event(db, seeded_property, make_account):
    g = await make_account("guest", "g-s3")
    r1, _ = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    before = (await db.execute(
        select(func.count()).select_from(Event))).scalar_one()
    await svc.update_stay(db, st.id, check_out=co + timedelta(days=1),
                          actor=None)
    after = (await db.execute(
        select(func.count()).select_from(Event))).scalar_one()
    assert before == after
    with pytest.raises(NotFoundError):
        await svc.update_stay(db, uuid.uuid4(), actor=None)


async def test_relocate(db, seeded_property, make_account):
    g = await make_account("guest", "g-s4")
    r1, r2 = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    with pytest.raises(NotFoundError):
        await svc.relocate_stay(db, uuid.uuid4(), r2.id, actor=None)
    with pytest.raises(ConflictError):
        await svc.relocate_stay(db, st.id, r1.id, actor=None)
    with pytest.raises(ValidationError):
        await svc.relocate_stay(db, st.id, uuid.uuid4(), actor=None)
    await svc.relocate_stay(db, st.id, r2.id, actor=None)
    await db.flush()
    rel = (await db.execute(
        select(EventGuestRelocated))).scalars().one()
    assert rel.from_room_id == r1.id and rel.to_room_id == r2.id


async def test_checkout_then_recheckin(db, seeded_property, make_account):
    g = await make_account("guest", "g-s5")
    r1, r2 = await _rooms(db, seeded_property)
    ci, co = _win()
    st = await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)
    await db.flush()
    await svc.checkout_stay(db, st.id, actor=None)
    await db.flush()
    assert (await db.execute(
        select(func.count()).select_from(EventStayEnded))).scalar_one() == 1
    with pytest.raises(ConflictError):
        await svc.relocate_stay(db, st.id, r2.id, actor=None)
    await svc.create_stay(db, g.id, r1.id, ci, co, actor=None)  # allowed
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement** (`actor` may be `None` in unit tests or an `Actor` with `.id: str`; pass `uuid.UUID(actor.id)` when present)

```python
# conduit/supervisor/services/stays.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.shared.models.account import Account
from conduit.supervisor.dal import stays as dal, rooms as rdal, events as edal


def _actor_id(actor) -> uuid.UUID | None:
    aid = getattr(actor, "id", None)
    return uuid.UUID(str(aid)) if aid is not None else None


async def list_stays(s: AsyncSession, status=None, guest_id=None):
    return await dal.list_stays(s, status=status, guest_id=guest_id)


async def _require_guest(s, guest_account_id):
    g = await s.get(Account, guest_account_id)
    if g is None or g.role != "guest" or g.status != "active":
        raise ValidationError("guest account invalid")


async def _require_room(s, room_id):
    if await rdal.get_room(s, room_id) is None:
        raise ValidationError("room does not exist")


async def create_stay(s: AsyncSession, guest_account_id: uuid.UUID,
                        room_id: uuid.UUID, check_in: datetime,
                        check_out: datetime, *, actor):
    await _require_guest(s, guest_account_id)
    await _require_room(s, room_id)
    if await dal.get_active_stay_for_guest(s, guest_account_id) is not None:
        raise ConflictError("guest already has an active stay")
    st = await dal.insert_stay(s, guest_account_id, room_id,
                                check_in, check_out)
    await s.flush()
    ev = await edal.insert_event(s, type="stay_created",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_stay_created(s, ev.id, st.id)
    return st


async def update_stay(s: AsyncSession, stay_id: uuid.UUID, *,
                       check_in: datetime | None = None,
                       check_out: datetime | None = None, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    return await dal.update_stay_fields(s, st, check_in=check_in,
                                         check_out=check_out)


async def relocate_stay(s: AsyncSession, stay_id: uuid.UUID,
                          new_room_id: uuid.UUID, *, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    if st.status != "active":
        raise ConflictError("stay is not active")
    await _require_room(s, new_room_id)
    if st.room_id == new_room_id:
        raise ConflictError("already in that room")
    from_room = st.room_id
    await dal.set_stay_room(s, st, new_room_id)
    await s.flush()
    ev = await edal.insert_event(s, type="guest_relocated",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_guest_relocated(s, ev.id, st.id,
                                       from_room, new_room_id)
    return st


async def checkout_stay(s: AsyncSession, stay_id: uuid.UUID, *, actor):
    st = await dal.get_stay(s, stay_id)
    if st is None:
        raise NotFoundError("stay not found")
    if st.status != "active":
        raise ConflictError("stay is not active")
    await dal.set_stay_status(s, st, "ended")
    await s.flush()
    ev = await edal.insert_event(s, type="stay_ended",
                                  actor_account_id=_actor_id(actor))
    await s.flush()
    await edal.insert_stay_ended(s, ev.id, st.id)
    return st
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_svc_stays.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/stays.py tests/binding/test_svc_stays.py
git commit -m "feat(supervisor/services): stays — guards + events (async)"
```

### Task 12: `resolve_ambient` + AuthUser + `/me`

**Files:** Modify `conduit/public/services/auth.py`, `conduit/public/schemas/auth.py`, `conduit/public/api/auth.py`; Test `tests/binding/test_ambient.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_ambient.py
from datetime import datetime, timedelta, timezone
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as stsvc


async def test_me_carries_ambient_no_relogin(
    db, client, make_account, login, seeded_property,
):
    await make_account("supervisor", "sup-a", "pw-123456")
    g = await make_account("guest", "guest-a", "pw-123456")
    sec = await ssvc.create_section(db, seeded_property.id, "North",
                                    actor=None)
    await db.flush()
    r1 = await rsvc.create_room(db, "304", sec.id, actor=None)
    sec2 = await ssvc.create_section(db, seeded_property.id, "South",
                                     actor=None)
    await db.flush()
    r2 = await rsvc.create_room(db, "511", sec2.id, actor=None)
    await db.flush()
    n = datetime.now(timezone.utc)
    st = await stsvc.create_stay(db, g.id, r1.id, n, n + timedelta(days=1),
                                 actor=None)
    await db.commit()

    await login("guest-a", "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "304" and me["section_label"] == "North"

    await stsvc.relocate_stay(db, st.id, r2.id, actor=None)
    await db.commit()
    me2 = (await client.get("/api/auth/me")).json()  # same cookie, no re-login
    assert me2["room_label"] == "511" and me2["section_label"] == "South"


async def test_me_ambient_null_for_supervisor(client, make_account, login):
    await make_account("supervisor", "sup-b", "pw-123456")
    await login("sup-b", "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me.get("room_id") is None
```

- [ ] **Step 2: Run, expect fail.** → KeyError/None (no ambient fields)

- [ ] **Step 3: Implement**

Append to `conduit/public/services/auth.py`:

```python
from conduit.core.deps import Actor
from conduit.public.dal import bindings as _bindings


async def resolve_ambient(s: AsyncSession, actor: Actor) -> dict | None:
    if actor.role != "guest":
        return None
    trio = await _bindings.get_active_binding_for_guest(s, actor.id)
    if trio is None:
        return None
    stay, room, section = trio
    return {"stay_id": stay.id, "room_id": room.id,
            "room_label": room.label, "section_id": section.id,
            "section_label": section.label}
```

In `conduit/public/schemas/auth.py`, add to `AuthUser` after `display_name` (`import uuid` is already present):

```python
    stay_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    room_label: str | None = None
    section_id: uuid.UUID | None = None
    section_label: str | None = None
```

In `conduit/public/api/auth.py`, replace the `me` handler body:

```python
@router.get("/me", response_model=AuthUser)
async def me(actor: Actor = Depends(current_actor),
             s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.current_account(s, actor.id)
    base = AuthUser.model_validate(acc).model_dump()
    amb = await svc.resolve_ambient(s, actor) or {}
    return AuthUser(**base, **amb)
```

(`svc.resolve_ambient` queries by `actor.id` — the JWT `sub` string — which SQLAlchemy coerces for the `UUID` column, exactly as auth's `get_by_id` already does. `login` still returns `AuthUser` with `None` ambient; the SPA bootstraps via `/me`, which is fine.)

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_ambient.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/public/services/auth.py conduit/public/schemas/auth.py conduit/public/api/auth.py tests/binding/test_ambient.py
git commit -m "feat(public): /auth/me carries guest ambient (re-resolved per request)"
```

### Task 13: Supervisor schemas

**Files:** Create `conduit/supervisor/schemas/binding.py`; Test `tests/binding/test_schemas.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_schemas.py
import pytest, pydantic
from conduit.supervisor.schemas.binding import SectionOut


def test_section_out_forbids_extra():
    with pytest.raises(pydantic.ValidationError):
        SectionOut(id="00000000-0000-0000-0000-000000000000", label="N",
                   room_count=0, created_at="2026-01-01T00:00:00Z", x=1)
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/schemas/binding.py
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class _B(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SectionCreate(_B):
    label: str


class SectionOut(_B):
    id: uuid.UUID
    label: str
    room_count: int
    created_at: datetime


class RoomCreate(_B):
    label: str
    section_id: uuid.UUID


class RoomUpdate(_B):
    label: str | None = None
    section_id: uuid.UUID | None = None


class RoomOut(_B):
    id: uuid.UUID
    label: str
    section_id: uuid.UUID
    section_label: str
    created_at: datetime


class StayCreate(_B):
    guest_account_id: uuid.UUID
    room_id: uuid.UUID
    check_in: datetime
    check_out: datetime


class StayUpdate(_B):
    check_in: datetime | None = None
    check_out: datetime | None = None


class RelocateIn(_B):
    new_room_id: uuid.UUID


class StayOut(_B):
    id: uuid.UUID
    guest_account_id: uuid.UUID
    guest_display_name: str
    room_id: uuid.UUID
    room_label: str
    section_id: uuid.UUID
    section_label: str
    check_in: datetime
    check_out: datetime
    status: str
    created_at: datetime
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_schemas.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/schemas/binding.py tests/binding/test_schemas.py
git commit -m "feat(supervisor/schemas): binding request/response (extra=forbid)"
```

### Task 14: Supervisor API — `binding.py` + register

**Files:** Create `conduit/supervisor/api/binding.py`; Modify `conduit/supervisor/api/__init__.py`; Test `tests/binding/test_api.py`

- [ ] **Step 1: Failing test** (authed-supervisor chain via `make_account`+`login`+`client`)

```python
# tests/binding/test_api.py
import uuid
import pytest


@pytest.fixture()
async def sup(make_account, login):
    await make_account("supervisor", "sup-api", "pw-123456")
    await login("sup-api", "pw-123456")


async def test_sections_rooms_flow(client, sup):
    r = await client.post("/api/supervisor/sections", json={"label": "North"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (await client.get("/api/supervisor/sections")).status_code == 200
    assert (await client.post("/api/supervisor/sections",
                              json={"label": "north"})).status_code == 409
    rn = await client.patch(f"/api/supervisor/sections/{sid}",
                            json={"label": "N"})
    assert rn.status_code == 200 and rn.json()["label"] == "N"
    rm = await client.post("/api/supervisor/rooms",
                           json={"label": "304", "section_id": sid})
    assert rm.status_code == 201
    assert (await client.get(
        f"/api/supervisor/rooms?section_id={sid}")).status_code == 200
    assert (await client.delete(
        f"/api/supervisor/sections/{sid}")).status_code == 405


async def test_stays_flow(client, sup):
    sid = (await client.post("/api/supervisor/sections",
                             json={"label": "N"})).json()["id"]
    rid = (await client.post("/api/supervisor/rooms",
                             json={"label": "304", "section_id": sid}
                             )).json()["id"]
    rid2 = (await client.post("/api/supervisor/rooms",
                              json={"label": "511", "section_id": sid}
                              )).json()["id"]
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": f"g{uuid.uuid4().hex[:8]}",
        "display_name": "G", "password": "pw-123456"})).json()["id"]
    st = (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).json()["id"]
    assert (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).status_code == 409
    mv = await client.post(f"/api/supervisor/stays/{st}/relocate",
                           json={"new_room_id": rid2})
    assert mv.status_code == 200 and mv.json()["room_id"] == rid2
    assert (await client.post(f"/api/supervisor/stays/{st}/relocate",
                              json={"new_room_id": rid2})).status_code == 409
    co = await client.post(f"/api/supervisor/stays/{st}/checkout")
    assert co.status_code == 200 and co.json()["status"] == "ended"
    assert (await client.post(
        f"/api/supervisor/stays/{uuid.uuid4()}/checkout")).status_code == 404


async def test_unauth_and_forbidden(client, make_account, login):
    assert (await client.get("/api/supervisor/sections")).status_code == 401
    await make_account("guest", "g-forbid", "pw-123456")
    await login("g-forbid", "pw-123456")
    assert (await client.get("/api/supervisor/sections")).status_code == 403
```

- [ ] **Step 2: Run, expect fail.** → 404 routes

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/api/binding.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from conduit.core.deps import Actor, db_session, require_roles
from conduit.shared.models.account import Account
from conduit.shared.models.property import Property
from conduit.supervisor.dal import rooms as rdal, sections as sdal
from conduit.supervisor.schemas.binding import (
    RelocateIn, RoomCreate, RoomOut, RoomUpdate, SectionCreate, SectionOut,
    StayCreate, StayOut, StayUpdate,
)
from conduit.supervisor.services import (
    rooms as rsvc, sections as ssvc, stays as stsvc,
)

router = APIRouter(tags=["supervisor-binding"])
_sup = require_roles("supervisor", "duty_manager")


async def _property_id(s: AsyncSession) -> uuid.UUID:
    return (await s.execute(select(Property.id))).scalars().first()


def _section_out(sec, count) -> SectionOut:
    return SectionOut(id=sec.id, label=sec.label, room_count=count,
                      created_at=sec.created_at)


async def _room_out(s, r) -> RoomOut:
    sec = await sdal.get_section(s, r.section_id)
    return RoomOut(id=r.id, label=r.label, section_id=r.section_id,
                   section_label=sec.label, created_at=r.created_at)


async def _stay_out(s, st) -> StayOut:
    room = await rdal.get_room(s, st.room_id)
    sec = await sdal.get_section(s, room.section_id)
    guest = await s.get(Account, st.guest_account_id)
    return StayOut(
        id=st.id, guest_account_id=st.guest_account_id,
        guest_display_name=guest.display_name,
        room_id=room.id, room_label=room.label,
        section_id=sec.id, section_label=sec.label,
        check_in=st.check_in, check_out=st.check_out,
        status=st.status, created_at=st.created_at)


@router.get("/sections", response_model=list[SectionOut])
async def list_sections(actor: Actor = Depends(_sup),
                        s: AsyncSession = Depends(db_session)):
    return [_section_out(sec, c) for sec, c in await ssvc.list_sections(s)]


@router.post("/sections", response_model=SectionOut, status_code=201)
async def create_section(body: SectionCreate, actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    sec = await ssvc.create_section(s, await _property_id(s),
                                    body.label, actor=actor)
    await s.commit()
    return _section_out(sec, 0)


@router.patch("/sections/{section_id}", response_model=SectionOut)
async def rename_section(section_id: uuid.UUID, body: SectionCreate,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    sec = await ssvc.rename_section(s, section_id, body.label, actor=actor)
    await s.commit()
    counts = {x.id: c for x, c in await ssvc.list_sections(s)}
    return _section_out(sec, counts.get(sec.id, 0))


@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(section_id: uuid.UUID | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return [await _room_out(s, r)
            for r in await rsvc.list_rooms(s, section_id)]


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(body: RoomCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    r = await rsvc.create_room(s, body.label, body.section_id, actor=actor)
    await s.commit()
    return await _room_out(s, r)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(room_id: uuid.UUID, body: RoomUpdate,
                      actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    r = await rsvc.update_room(s, room_id, label=body.label,
                               section_id=body.section_id, actor=actor)
    await s.commit()
    return await _room_out(s, r)


@router.get("/stays", response_model=list[StayOut])
async def list_stays(status: str | None = None,
                     guest_id: uuid.UUID | None = None,
                     actor: Actor = Depends(_sup),
                     s: AsyncSession = Depends(db_session)):
    return [await _stay_out(s, st)
            for st in await stsvc.list_stays(s, status=status,
                                             guest_id=guest_id)]


@router.post("/stays", response_model=StayOut, status_code=201)
async def create_stay(body: StayCreate, actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    st = await stsvc.create_stay(s, body.guest_account_id, body.room_id,
                                 body.check_in, body.check_out, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.patch("/stays/{stay_id}", response_model=StayOut)
async def update_stay(stay_id: uuid.UUID, body: StayUpdate,
                      actor: Actor = Depends(_sup),
                      s: AsyncSession = Depends(db_session)):
    st = await stsvc.update_stay(s, stay_id, check_in=body.check_in,
                                 check_out=body.check_out, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.post("/stays/{stay_id}/relocate", response_model=StayOut)
async def relocate(stay_id: uuid.UUID, body: RelocateIn,
                   actor: Actor = Depends(_sup),
                   s: AsyncSession = Depends(db_session)):
    st = await stsvc.relocate_stay(s, stay_id, body.new_room_id, actor=actor)
    await s.commit()
    return await _stay_out(s, st)


@router.post("/stays/{stay_id}/checkout", response_model=StayOut)
async def checkout(stay_id: uuid.UUID, actor: Actor = Depends(_sup),
                  s: AsyncSession = Depends(db_session)):
    st = await stsvc.checkout_stay(s, stay_id, actor=actor)
    await s.commit()
    return await _stay_out(s, st)
```

In `conduit/supervisor/api/__init__.py`, add the import and include it (mirror the existing `router.include_router(...)` lines):

```python
from conduit.supervisor.api.binding import router as binding_router
# ... after the existing includes:
router.include_router(binding_router)
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_api.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/api/binding.py conduit/supervisor/api/__init__.py tests/binding/test_api.py
git commit -m "feat(supervisor/api): binding routes (per-handler gate, commit at edge)"
```

### Task 15: Seed `ensure_property`

**Files:** Modify `conduit/seed.py`; Test `tests/binding/test_seed_property.py`

- [ ] **Step 1: Failing test**

```python
# tests/binding/test_seed_property.py
from sqlalchemy import func, select
from conduit.shared.models.property import Property
from conduit.seed import ensure_property


async def test_ensure_property_idempotent(db):
    await ensure_property(db)
    await ensure_property(db)
    await db.commit()
    n = (await db.execute(
        select(func.count()).select_from(Property))).scalar_one()
    assert n == 1
```

- [ ] **Step 2: Run, expect fail.** → ImportError

- [ ] **Step 3: Implement** — add to `conduit/seed.py` and call from `_main` before `await run(...)`:

```python
from sqlalchemy import select as _select
from conduit.shared.models.property import Property as _Property


async def ensure_property(s, name: str = "Conduit Property") -> _Property:
    existing = (await s.execute(_select(_Property))).scalars().first()
    if existing is not None:
        return existing
    p = _Property(name=name)
    s.add(p)
    await s.flush()
    return p
```

In `_main`, before `await run(...)`:

```python
        await ensure_property(s)
```

- [ ] **Step 4: Run, expect pass.** `./.venv/bin/pytest tests/binding/test_seed_property.py -q`

- [ ] **Step 5: Commit**

```bash
git add conduit/seed.py tests/binding/test_seed_property.py
git commit -m "feat(seed): idempotent ensure_property (async)"
```

### Task 16: Invariants + e2e sentinel + regenerate contract snapshot

**Files:** Create `tests/binding/test_invariants.py`, `tests/binding/test_e2e_journey.py`; regenerate `tests/api/contract_snapshot.json`

- [ ] **Step 1: Invariants**

```python
# tests/binding/test_invariants.py
import uuid
import pytest
from sqlalchemy import text
from conduit.supervisor.dal import sections as sdal, rooms as rdal


async def test_partial_unique_index_blocks_second_active(
    db, seeded_property, make_account,
):
    g = await make_account("guest", "g-inv-1")
    s = await sdal.insert_section(db, seeded_property.id, "N")
    await db.flush()
    r = await rdal.insert_room(db, s.id, "304")
    await db.flush()
    for _ in range(2):
        await db.execute(text(
            "insert into stay (guest_account_id,room_id,check_in,check_out,"
            "status) values (:g,:r,now(),now(),'active')"),
            {"g": str(g.id), "r": str(r.id)})
    with pytest.raises(Exception):
        await db.flush()
    await db.rollback()


async def test_event_dal_has_no_mutation_path():
    from conduit.supervisor.dal import events as edal
    assert not any(n.startswith(("update_", "delete_")) for n in dir(edal))


async def test_section_is_derived_no_stay_write(
    client, make_account, login,
):
    await make_account("supervisor", "sup-inv", "pw-123456")
    await login("sup-inv", "pw-123456")
    sid = (await client.post("/api/supervisor/sections",
                             json={"label": "N"})).json()["id"]
    rid = (await client.post("/api/supervisor/rooms",
                             json={"label": "304", "section_id": sid}
                             )).json()["id"]
    sid2 = (await client.post("/api/supervisor/sections",
                              json={"label": "S"})).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "G",
        "password": "pw-123456"})).json()["id"]
    await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] == "N"
    await login("sup-inv", "pw-123456")
    await client.patch(f"/api/supervisor/rooms/{rid}",
                       json={"section_id": sid2})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] == "S"
```

- [ ] **Step 2: E2E journey sentinel**

```python
# tests/binding/test_e2e_journey.py
import uuid


async def test_full_journey(client, make_account, login):
    await make_account("supervisor", "sup-e2e", "pw-123456")
    await login("sup-e2e", "pw-123456")
    s1 = (await client.post("/api/supervisor/sections",
                            json={"label": "North"})).json()["id"]
    r1 = (await client.post("/api/supervisor/rooms",
                            json={"label": "304", "section_id": s1}
                            )).json()["id"]
    s2 = (await client.post("/api/supervisor/sections",
                            json={"label": "South"})).json()["id"]
    r2 = (await client.post("/api/supervisor/rooms",
                            json={"label": "511", "section_id": s2}
                            )).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = (await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "Guest",
        "password": "pw-123456"})).json()["id"]
    st = (await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})).json()["id"]

    await login(uname, "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "304" and me["section_label"] == "North"

    await login("sup-e2e", "pw-123456")
    await client.post(f"/api/supervisor/stays/{st}/relocate",
                      json={"new_room_id": r2})
    await login(uname, "pw-123456")
    me = (await client.get("/api/auth/me")).json()
    assert me["room_label"] == "511" and me["section_label"] == "South"

    await login("sup-e2e", "pw-123456")
    await client.patch(f"/api/supervisor/rooms/{r2}",
                       json={"section_id": s1})
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json()["section_label"] \
        == "North"

    await login("sup-e2e", "pw-123456")
    await client.post(f"/api/supervisor/stays/{st}/checkout")
    await login(uname, "pw-123456")
    assert (await client.get("/api/auth/me")).json().get("room_id") is None

    await login("sup-e2e", "pw-123456")
    again = await client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-06-01T14:00:00Z",
        "check_out": "2026-06-03T11:00:00Z"})
    assert again.status_code == 201
```

- [ ] **Step 3: Regenerate the contract snapshot (intentional)**

```bash
rm tests/api/contract_snapshot.json
./.venv/bin/pytest tests/api/test_security_guards.py -q   # recreates + skips
./.venv/bin/pytest tests/api/test_security_guards.py -q   # now enforces, green
```

- [ ] **Step 4: Run the binding suite + the inherited guards**

Run: `./.venv/bin/pytest tests/binding tests/api/test_security_guards.py -q`
Expected: PASS (new routes swept by the auth-coverage guard; snapshot matches the regenerated file; `secret_hash` substring guard still green).

- [ ] **Step 5: Commit**

```bash
git add tests/binding/test_invariants.py tests/binding/test_e2e_journey.py tests/api/contract_snapshot.json
git commit -m "test(binding): invariants + e2e sentinel + regenerated contract snapshot"
```

### Task 17: Full backend suite + lint

- [ ] **Step 1: Whole suite**

Run: `./.venv/bin/pytest -q`
Expected: all green incl. `--cov-fail-under=90` (binding modules are inside the existing `conduit.public`/`conduit.supervisor`/`conduit.shared.models` cov scope), leak sentinel silent.

- [ ] **Step 2: Lint/type (project tools, if configured in `pyproject.toml`)**

Run: `./.venv/bin/ruff check conduit && ./.venv/bin/mypy conduit` (fix findings in this slice's files only).

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "chore(binding): lint/type clean" || echo "nothing to commit"
```

---

# PHASE 2 — Frontend

> Paths relative to `/workspace/Conduit-stay-binding/frontend`. Verified real primitive APIs on `main`: `PageHeader{title,description?,actions?}`, `EmptyState{title,hint?,action?}`, `ErrorState{title?,onRetry?}`, `DataTableShell{state,toolbar?,table,cards,onRetry?,emptyTitle,emptyHint?}`, `<Confirm open onOpenChange title description? confirmLabel? onConfirm>`, `api.get/post/patch/del`. Do **not** re-add existing `components/ui/*`.

### Task 18: Install net-new shadcn + monochrome pass

- [ ] **Step 1: Install** (verified absent on `main`)

```bash
cd /workspace/Conduit-stay-binding/frontend
npx shadcn@latest add popover calendar command accordion
```

- [ ] **Step 2: Monochrome/tighten pass** on the four new files: neutral focus rings (`ring`), no chromatic states, `shadow-sm` max, project `--radius` tokens. Do **not** touch `index.css` (a separate follow-up per spec §9).

- [ ] **Step 3: Build check** — `npx tsc -b && npx eslint src --max-warnings 0` → clean

- [ ] **Step 4: Commit**

```bash
git add src/components/ui/popover.tsx src/components/ui/calendar.tsx src/components/ui/command.tsx src/components/ui/accordion.tsx
git commit -m "feat(ui): popover/calendar/command/accordion (monochrome)"
```

### Task 19: Composed patterns

**Files:** Create `src/components/common/combobox-field.tsx`, `src/components/common/date-range-field.tsx`

- [ ] **Step 1: `combobox-field.tsx`**

```tsx
// src/components/common/combobox-field.tsx
import { useState } from "react"
import { Check, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command"
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover"

export type ComboOption = { value: string; label: string }

export function ComboboxField({
  options, value, onChange, placeholder = "Select…", emptyText = "None found",
}: {
  options: ComboOption[]
  value: string | null
  onChange: (v: string) => void
  placeholder?: string
  emptyText?: string
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open}
          className="w-full justify-between font-normal">
          {selected ? selected.label : placeholder}
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0">
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <CommandEmpty>{emptyText}</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem key={o.value} value={o.label}
                  onSelect={() => { onChange(o.value); setOpen(false) }}>
                  <Check className={cn("mr-2 size-4",
                    o.value === value ? "opacity-100" : "opacity-0")} />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
```

- [ ] **Step 2: `date-range-field.tsx`**

```tsx
// src/components/common/date-range-field.tsx
import { CalendarIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover"

export type DateRange = { from?: Date; to?: Date }

const fmt = (d?: Date) => (d ? d.toISOString().slice(0, 10) : "—")

export function DateRangeField({
  value, onChange,
}: { value: DateRange; onChange: (r: DateRange) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline"
          className="w-full justify-start font-normal">
          <CalendarIcon className="mr-2 size-4" />
          {fmt(value.from)} → {fmt(value.to)}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="range"
          selected={{ from: value.from, to: value.to }}
          onSelect={(r) => onChange({ from: r?.from, to: r?.to })}
          numberOfMonths={2} />
      </PopoverContent>
    </Popover>
  )
}
```

- [ ] **Step 3: Build check + commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`

```bash
git add src/components/common/combobox-field.tsx src/components/common/date-range-field.tsx
git commit -m "feat(ui): combobox-field + date-range-field"
```

### Task 20: Hooks + invalidation helper

**Files:** Create `src/shell/supervisor/hooks/{invalidate-binding,use-sections,use-rooms,use-stays}.ts`

- [ ] **Step 1: Implement** (mirrors `use-accounts.ts`)

```ts
// src/shell/supervisor/hooks/invalidate-binding.ts
import type { QueryClient } from "@tanstack/react-query"
export function invalidateBinding(
  qc: QueryClient, keys: Array<"sections" | "rooms" | "stays">,
) { for (const k of keys) qc.invalidateQueries({ queryKey: [k] }) }
```

```ts
// src/shell/supervisor/hooks/use-sections.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Section = {
  id: string; label: string; room_count: number; created_at: string
}
export function useSections() {
  return useQuery({
    queryKey: ["sections"],
    queryFn: () => api.get<Section[]>("/supervisor/sections"),
  })
}
export function useCreateSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) =>
      api.post<Section>("/supervisor/sections", { label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}
export function useRenameSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; label: string }) =>
      api.patch<Section>(`/supervisor/sections/${v.id}`, { label: v.label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}
```

```ts
// src/shell/supervisor/hooks/use-rooms.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Room = {
  id: string; label: string; section_id: string
  section_label: string; created_at: string
}
export function useRooms(sectionId?: string) {
  return useQuery({
    queryKey: ["rooms", sectionId ?? null],
    queryFn: () => api.get<Room[]>(
      `/supervisor/rooms${sectionId ? `?section_id=${sectionId}` : ""}`),
  })
}
export function useCreateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { label: string; section_id: string }) =>
      api.post<Room>("/supervisor/rooms", v),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}
export function useUpdateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...b }: {
      id: string; label?: string; section_id?: string
    }) => api.patch<Room>(`/supervisor/rooms/${id}`, b),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}
```

```ts
// src/shell/supervisor/hooks/use-stays.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Stay = {
  id: string; guest_account_id: string; guest_display_name: string
  room_id: string; room_label: string; section_id: string
  section_label: string; check_in: string; check_out: string
  status: "active" | "ended"; created_at: string
}
export function useStays(status?: string, guestId?: string) {
  const qs = new URLSearchParams()
  if (status) qs.set("status", status)
  if (guestId) qs.set("guest_id", guestId)
  const s = qs.toString()
  return useQuery({
    queryKey: ["stays", status ?? null, guestId ?? null],
    queryFn: () => api.get<Stay[]>(`/supervisor/stays${s ? `?${s}` : ""}`),
  })
}
export function useCreateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { guest_account_id: string; room_id: string
      check_in: string; check_out: string }) =>
      api.post<Stay>("/supervisor/stays", v),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
export function useRelocateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; new_room_id: string }) =>
      api.post<Stay>(`/supervisor/stays/${v.id}/relocate`,
        { new_room_id: v.new_room_id }),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
export function useCheckoutStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Stay>(`/supervisor/stays/${id}/checkout`, {}),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
```

- [ ] **Step 2: Build check + commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`

```bash
git add src/shell/supervisor/hooks/invalidate-binding.ts src/shell/supervisor/hooks/use-sections.ts src/shell/supervisor/hooks/use-rooms.ts src/shell/supervisor/hooks/use-stays.ts
git commit -m "feat(supervisor/hooks): sections/rooms/stays + invalidation"
```

### Task 21: Sections page

**Files:** Create `src/shell/supervisor/pages/sections.tsx`

- [ ] **Step 1: Implement** (real primitive APIs: `PageHeader actions=`, `EmptyState title/hint`, `ErrorState onRetry`)

```tsx
// src/shell/supervisor/pages/sections.tsx
import { useState } from "react"
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import {
  useSections, useCreateSection, useRenameSection,
} from "@/shell/supervisor/hooks/use-sections"
import { useRooms, useCreateRoom } from "@/shell/supervisor/hooks/use-rooms"

function Rooms({ sectionId }: { sectionId: string }) {
  const rooms = useRooms(sectionId)
  const create = useCreateRoom()
  const [label, setLabel] = useState("")
  if (rooms.isLoading) return <Skeleton className="h-8 w-full" />
  if (rooms.isError) return <ErrorState onRetry={rooms.refetch} />
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(rooms.data ?? []).map((r) => (
          <span key={r.id}
            className="rounded-md border px-2 py-1 text-xs font-medium">
            {r.label}
          </span>
        ))}
        {rooms.data?.length === 0 && (
          <span className="text-muted-foreground text-xs">No rooms yet.</span>
        )}
      </div>
      <form className="flex gap-2" onSubmit={(e) => {
        e.preventDefault()
        if (label.trim())
          create.mutate({ label: label.trim(), section_id: sectionId },
            { onSuccess: () => setLabel("") })
      }}>
        <Input value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="Add room (e.g. 304)" className="h-9 max-w-[12rem]" />
        <Button type="submit" size="sm" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add room"}
        </Button>
      </form>
    </div>
  )
}

function SectionLabel({ id, label }: { id: string; label: string }) {
  const rename = useRenameSection()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(label)
  if (!editing)
    return (
      <span className="font-medium"
        onClick={(e) => { e.stopPropagation(); setEditing(true) }}>
        {label}
      </span>
    )
  return (
    <Input autoFocus value={val} className="h-7 max-w-[14rem]"
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => {
        setEditing(false)
        if (val.trim() && val !== label)
          rename.mutate({ id, label: val.trim() })
      }} />
  )
}

export function SectionsPage() {
  const sections = useSections()
  const create = useCreateSection()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState("")
  const total = sections.data?.length ?? 0
  const rooms = (sections.data ?? []).reduce((n, s) => n + s.room_count, 0)
  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader title="Sections"
        description={`${total} sections · ${rooms} rooms`}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button>New section</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New section</DialogTitle>
              </DialogHeader>
              <Input value={label} onChange={(e) => setLabel(e.target.value)}
                placeholder="Section label (e.g. North Wing)" />
              <DialogFooter>
                <Button disabled={create.isPending || !label.trim()}
                  onClick={() => create.mutate(label.trim(), {
                    onSuccess: () => { setLabel(""); setOpen(false) },
                  })}>
                  {create.isPending ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        } />
      {sections.isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      )}
      {sections.isError && <ErrorState onRetry={sections.refetch} />}
      {sections.data?.length === 0 && (
        <EmptyState title="No sections yet"
          hint="Create a section to start mapping rooms." />
      )}
      {!!sections.data?.length && (
        <Accordion type="multiple" className="w-full">
          {sections.data.map((s) => (
            <AccordionItem key={s.id} value={s.id}>
              <AccordionTrigger className="text-sm">
                <span className="flex w-full items-center justify-between pr-3">
                  <SectionLabel id={s.id} label={s.label} />
                  <span className="text-muted-foreground text-xs">
                    {s.room_count} rooms
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <Rooms sectionId={s.id} />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build check + commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`

```bash
git add src/shell/supervisor/pages/sections.tsx
git commit -m "feat(supervisor/pages): Sections (accordion + room chips)"
```

### Task 22: Provisioning / Check-in page

**Files:** Create `src/shell/supervisor/pages/provisioning.tsx`

- [ ] **Step 1: Implement** (mirrors `manage-accounts.tsx`: compute `state`, pass `<Table>`+`cards`; `<Confirm>` controlled; **`useStays('active')` called once at top level — no nested hook**)

```tsx
// src/shell/supervisor/pages/provisioning.tsx
import { useMemo, useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { Confirm } from "@/components/common/confirm"
import { ComboboxField } from "@/components/common/combobox-field"
import {
  DateRangeField, type DateRange,
} from "@/components/common/date-range-field"
import {
  useStays, useCreateStay, useRelocateStay, useCheckoutStay, type Stay,
} from "@/shell/supervisor/hooks/use-stays"
import { useRooms } from "@/shell/supervisor/hooks/use-rooms"
import { useAccounts } from "@/shell/supervisor/hooks/use-accounts"

export function ProvisioningPage() {
  const [status, setStatus] = useState<"active" | "ended" | "">("active")
  const list = useStays(status || undefined)
  const activeList = useStays("active")           // top-level, once
  const rooms = useRooms()
  const guests = useAccounts("guest")
  const createStay = useCreateStay()
  const relocate = useRelocateStay()
  const checkout = useCheckoutStay()
  const [open, setOpen] = useState(false)
  const [confirmStay, setConfirmStay] = useState<Stay | null>(null)

  const activeGuestIds = useMemo(
    () => new Set((activeList.data ?? []).map((s) => s.guest_account_id)),
    [activeList.data])
  const guestOptions = (guests.data ?? [])
    .filter((g) => !activeGuestIds.has(g.id))
    .map((g) => ({ value: g.id, label: g.display_name }))
  const roomOptions = (rooms.data ?? []).map(
    (r) => ({ value: r.id, label: `${r.label} · ${r.section_label}` }))

  const state = list.isLoading ? "loading" : list.isError ? "error"
    : (list.data?.length ?? 0) === 0 ? "empty" : "ready"

  const actions = (st: Stay) =>
    st.status === "active" ? (
      <RowActions
        roomOptions={roomOptions.filter((o) => o.value !== st.room_id)}
        current={`${st.room_label} · ${st.section_label}`}
        onMove={(rid) => relocate.mutate({ id: st.id, new_room_id: rid },
          { onSuccess: () => toast.success("Guest moved") })}
        onCheckout={() => setConfirmStay(st)} />
    ) : <span className="text-muted-foreground text-xs">ended</span>

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="Provisioning"
        description={`${list.data?.length ?? 0} ${status || "all"} stays`}
        actions={
          <CheckInDialog open={open} setOpen={setOpen}
            guestOptions={guestOptions} roomOptions={roomOptions}
            pending={createStay.isPending}
            onCreate={(v) => createStay.mutate(v, {
              onSuccess: () => { setOpen(false); toast.success("Checked in") },
            })} />
        } />
      <DataTableShell
        state={state} onRetry={list.refetch}
        emptyTitle="No stays" emptyHint="Check in a guest to begin."
        toolbar={
          <div className="flex gap-2">
            {(["active", "ended", ""] as const).map((sv) => (
              <Button key={sv || "all"} size="sm"
                variant={status === sv ? "default" : "outline"}
                onClick={() => setStatus(sv)}>
                {sv === "" ? "All" : sv[0].toUpperCase() + sv.slice(1)}
              </Button>
            ))}
          </div>
        }
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Guest</TableHead><TableHead>Room</TableHead>
                <TableHead>Section</TableHead><TableHead>Dates</TableHead>
                <TableHead>Status</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data?.map((st) => (
                <TableRow key={st.id}>
                  <TableCell className="font-medium">
                    {st.guest_display_name}</TableCell>
                  <TableCell>{st.room_label}</TableCell>
                  <TableCell>{st.section_label}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {st.check_in.slice(0, 10)} → {st.check_out.slice(0, 10)}
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1 text-xs">
                      <span className={st.status === "active"
                        ? "text-foreground" : "text-muted-foreground"}>
                        ●</span>{st.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">{actions(st)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={list.data?.map((st) => (
          <div key={st.id}
            className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">
                {st.guest_display_name}</div>
              <div className="text-muted-foreground text-xs">
                {st.room_label} · {st.section_label}
              </div>
            </div>
            {actions(st)}
          </div>
        ))} />
      <Confirm
        open={confirmStay !== null}
        onOpenChange={(o) => !o && setConfirmStay(null)}
        title="Check out?"
        description={confirmStay?.guest_display_name}
        confirmLabel="Check out"
        onConfirm={() => {
          if (confirmStay)
            checkout.mutate(confirmStay.id,
              { onSuccess: () => toast.success("Checked out") })
          setConfirmStay(null)
        }} />
    </div>
  )
}

function CheckInDialog({
  open, setOpen, guestOptions, roomOptions, onCreate, pending,
}: {
  open: boolean; setOpen: (b: boolean) => void
  guestOptions: { value: string; label: string }[]
  roomOptions: { value: string; label: string }[]
  onCreate: (v: { guest_account_id: string; room_id: string
    check_in: string; check_out: string }) => void
  pending: boolean
}) {
  const [guest, setGuest] = useState<string | null>(null)
  const [room, setRoom] = useState<string | null>(null)
  const [range, setRange] = useState<DateRange>({})
  const valid = guest && room && range.from && range.to
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>Check in guest</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Check in guest</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <ComboboxField options={guestOptions} value={guest}
            onChange={setGuest} placeholder="Select guest"
            emptyText="No guests without an active stay" />
          <ComboboxField options={roomOptions} value={room}
            onChange={setRoom} placeholder="Select room" />
          <DateRangeField value={range} onChange={setRange} />
        </div>
        <DialogFooter>
          <Button disabled={!valid || pending} onClick={() => onCreate({
            guest_account_id: guest!, room_id: room!,
            check_in: range.from!.toISOString(),
            check_out: range.to!.toISOString(),
          })}>{pending ? "Checking in…" : "Check in"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RowActions({
  roomOptions, current, onMove, onCheckout,
}: {
  roomOptions: { value: string; label: string }[]
  current: string
  onMove: (roomId: string) => void
  onCheckout: () => void
}) {
  const [moveOpen, setMoveOpen] = useState(false)
  const [target, setTarget] = useState<string | null>(null)
  return (
    <div className="flex justify-end gap-2">
      <Dialog open={moveOpen} onOpenChange={setMoveOpen}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">Move</Button>
        </DialogTrigger>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Move guest</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              {current} <span className="px-1">▶</span> new room
            </div>
            <ComboboxField options={roomOptions} value={target}
              onChange={setTarget} placeholder="Select new room" />
            <p className="text-muted-foreground text-xs">
              Re-binds the guest's room immediately. They see it on next
              refresh — no re-login.
            </p>
          </div>
          <DialogFooter>
            <Button disabled={!target} onClick={() => {
              onMove(target!); setMoveOpen(false)
            }}>Move</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Button size="sm" variant="ghost" onClick={onCheckout}>Check out</Button>
    </div>
  )
}
```

- [ ] **Step 2: Build check + commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`

```bash
git add src/shell/supervisor/pages/provisioning.tsx
git commit -m "feat(supervisor/pages): Provisioning (table/cards + move + check-in)"
```

### Task 23: Routes + nav

**Files:** Modify `src/App.tsx`, `src/shell/supervisor/nav.tsx`

- [ ] **Step 1: Add routes** — in `App.tsx`, import the pages and add child routes **before** the supervisor catch-all `<Route path="*" element={<SupervisorHome />} />`:

```tsx
import { SectionsPage } from "@/shell/supervisor/pages/sections"
import { ProvisioningPage } from "@/shell/supervisor/pages/provisioning"
// inside the /supervisor <Route> children, before <Route path="*" ...>:
<Route path="setup/sections" element={<SectionsPage />} />
<Route path="provisioning" element={<ProvisioningPage />} />
```

- [ ] **Step 2: Point the nav** — in `src/shell/supervisor/nav.tsx`, ensure a **Sections** entry targets `/supervisor/setup/sections` and a **Provisioning** entry targets `/supervisor/provisioning` (add/repoint within the existing `supervisorNav` structure; do not invent unrelated pages).

- [ ] **Step 3: Build + production bundle**

Run: `npx tsc -b && npx eslint src --max-warnings 0 && npx vite build`
Expected: clean; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx src/shell/supervisor/nav.tsx
git commit -m "feat(supervisor): wire Sections + Provisioning routes/nav"
```

---

# PHASE 3 — Finalize: full bench, push, PR

### Task 24: Full verification

- [ ] **Step 1: Backend** — `cd ../backend && ./.venv/bin/pytest -q` → all green, cov ≥ 90, leak sentinel silent.
- [ ] **Step 2: Frontend** — `cd ../frontend && npx tsc -b && npx eslint src --max-warnings 0 && npx vite build` → clean.
- [ ] **Step 3: Clean tree** — `cd /workspace/Conduit-stay-binding && git status -s` → empty.

### Task 25: Push + PR

- [ ] **Step 1: Push**

```bash
cd /workspace/Conduit-stay-binding
git push -u origin feat/stay-binding
```

- [ ] **Step 2: Open the PR (base = `main`; auth is merged)**

```bash
gh pr create --base main --head feat/stay-binding \
  --title "Stay/Binding slice — check-in & relocation" \
  --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-05-16-stay-binding-design.md.

- Relational Property/Section/Room/Stay + generic event base + 3 detail
  tables; 0002 migration with the partial unique index (one active
  stay per guest). All async, matching the merged auth code.
- core/exceptions: + ValidationError(422).
- supervisor/api/binding.py: sections/rooms/stays CRUD + relocate /
  checkout action endpoints (per-handler supervisor gate, commit at
  request edge). public /auth/me carries guest ambient
  {room,section,stay}, re-resolved per request (no re-login).
- Frontend: Sections (accordion + room chips) and Provisioning
  (DataTableShell + Move/Check-out + Check-in dialog); combobox-field
  + date-range-field.
- Tests: async layered (migration/DAL/services/API) + invariants +
  e2e journey sentinel; inherited auth-coverage + contract-snapshot
  guards (snapshot regenerated); FK-ordered teardown + leak sentinel;
  90% line cov gate.

Follow-ups (separate PRs, noted in spec §9/§12): global design-system
tightness; optional savepoint-rollback test isolation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr view --json url -q .url
```

---

## Self-review (performed)

- **Reconciled to merged `main`:** async `AsyncSession` everywhere; `ValidationError(422)` added (Task 2) and used for invalid guest/room; DAL add-only, services `await s.flush()`, handlers `await s.commit()`; routes via `supervisor/api/binding.py` registered in `__init__.py` with per-handler `_sup`; `AuthUser` extended in `public/schemas/auth.py`; `/me` builds ambient; tests async with `db`/`client`/`make_account`/`login` (no `supervisor_client`); `tests/binding/conftest.py` FK-ordered teardown before the inherited `Account` delete; contract snapshot regenerated by deleting `tests/api/contract_snapshot.json`; coverage is the existing global `--cov-fail-under=90`; migration `down_revision="0001"` with `server_default` ids/timestamps; frontend uses real primitive APIs (`PageHeader actions`, `EmptyState hint`, `DataTableShell state/table/cards`, `<Confirm>`, `api.del`) and the illegal nested `useStays` call is fixed (top-level `activeList`); PR base `main`.
- **Spec coverage:** every spec section maps to a task; deferred items stay deferred.
- **Placeholders:** none — assumptions replaced with the now-known concrete conventions.
- **Type consistency:** service `actor`-kwarg, async DAL signatures, schema/hook field names and `*_out` mappers consistent across tasks.
